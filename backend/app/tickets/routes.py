"""Owner-only ticket API with signed confirmation tokens and idempotent mutations."""
import base64
import csv
import hashlib
import hmac
import io
import json
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_csrf, require_owner
from app.config import get_settings
from app.db import get_db
from app.models import Competition, Fixture, IdempotencyKey, MarketOdds, Session, Team, Ticket, TicketRevision, TicketSelection

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])
TOKEN_TTL = 120

class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

class PreviewBody(StrictBody):
    action: Literal["create_ticket", "add_selection", "remove_selection", "archive_ticket"]
    payload: dict[str, Any]

class ConfirmBody(StrictBody):
    confirmation_token: str = Field(min_length=20, max_length=4000)

class CreatePayload(StrictBody):
    name: str = Field(min_length=1, max_length=160)
    notes: str | None = Field(default=None, max_length=2000)

class AddPayload(StrictBody):
    ticket_id: str = Field(min_length=1, max_length=36)
    fixture_id: str = Field(min_length=1, max_length=36)
    market_odds_id: str = Field(min_length=1, max_length=36)

class RemovePayload(StrictBody):
    ticket_id: str = Field(min_length=1, max_length=36)
    selection_id: str = Field(min_length=1, max_length=36)

class ArchivePayload(StrictBody):
    ticket_id: str = Field(min_length=1, max_length=36)

ACTION_MODELS = {
    "create_ticket": CreatePayload,
    "add_selection": AddPayload,
    "remove_selection": RemovePayload,
    "archive_ticket": ArchivePayload,
}

def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def _request_hash(action: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical({"action": action, "payload": payload})).hexdigest()

def _sign(payload: dict[str, Any]) -> str:
    body = base64.urlsafe_b64encode(_canonical(payload)).decode().rstrip("=")
    secret = get_settings().session_secret.get_secret_value().encode()
    signature = hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest()
    return body + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")

def _verify(token: str) -> dict[str, Any]:
    try:
        body, supplied = token.split(".", 1)
        secret = get_settings().session_secret.get_secret_value().encode()
        expected = hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest()
        actual = base64.urlsafe_b64decode(supplied + "=" * (-len(supplied) % 4))
        if not hmac.compare_digest(expected, actual):
            raise ValueError("signature")
        value = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if not isinstance(value, dict):
            raise ValueError("payload")
        return value
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(400, detail={"code":"invalid_confirmation_token","message":"Confirmation token is invalid."}) from exc

def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def _csv_safe(value: Any) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text

async def _revision(db: AsyncSession, ticket_id: str, before: dict[str, Any], after: dict[str, Any]) -> None:
    latest = await db.scalar(select(func.max(TicketRevision.revision)).where(TicketRevision.ticket_id == ticket_id))
    db.add(TicketRevision(ticket_id=ticket_id, revision=int(latest or 0) + 1, actor="owner",
                          before_state=before, after_state=after))

async def _validate_action(action: str, raw: dict[str, Any], db: AsyncSession) -> tuple[dict[str, Any], dict[str, Any]]:
    model = ACTION_MODELS.get(action)
    if model is None:
        raise HTTPException(422, detail={"code":"unsupported_ticket_action","message":"Ticket action is not supported."})
    try:
        payload = model.model_validate(raw).model_dump(mode="json")
    except ValidationError as exc:
        raise HTTPException(422, detail={"code":"invalid_ticket_action","message":"Ticket action payload is invalid."}) from exc

    if action == "create_ticket":
        payload["name"] = payload["name"].strip()
        if not payload["name"]:
            raise HTTPException(422, detail={"code":"invalid_ticket_name","message":"Ticket name cannot be blank."})
        return payload, {"summary":f"Create draft ticket “{payload['name']}”","warnings":[]}

    ticket = await db.get(Ticket, payload["ticket_id"])
    if ticket is None:
        raise HTTPException(404, detail={"code":"ticket_not_found","message":"Ticket not found."})
    if ticket.status != "draft":
        raise HTTPException(409, detail={"code":"ticket_not_editable","message":"Only draft tickets can be modified."})
    if action == "archive_ticket":
        return payload, {"summary":f"Archive draft ticket “{ticket.name}”","warnings":[]}
    if action == "remove_selection":
        selection = await db.get(TicketSelection, payload["selection_id"])
        if selection is None or selection.ticket_id != ticket.id:
            raise HTTPException(404, detail={"code":"selection_not_found","message":"Selection not found in this ticket."})
        return payload, {"summary":f"Remove {selection.market} / {selection.outcome} from “{ticket.name}”",
                         "warnings":["The revision audit retains the removed selection details."]}

    fixture = await db.get(Fixture, payload["fixture_id"])
    odds = await db.get(MarketOdds, payload["market_odds_id"])
    now = datetime.now(timezone.utc)
    kickoff = _utc(fixture.kickoff_at) if fixture else None
    observed = _utc(odds.observed_at) if odds else None
    if fixture is None or fixture.status != "scheduled" or kickoff is None or kickoff <= now:
        raise HTTPException(409, detail={"code":"fixture_not_bettable","message":"Fixture must be scheduled with a known future kickoff."})
    if odds is None or odds.fixture_id != fixture.id or Decimal(odds.decimal_odds) <= Decimal("1"):
        raise HTTPException(422, detail={"code":"invalid_odds_snapshot","message":"Odds snapshot does not match this fixture or is invalid."})
    if observed is None or observed > now or observed >= kickoff:
        raise HTTPException(409, detail={"code":"stale_odds_snapshot","message":"Odds snapshot is not a valid pre-kickoff observation."})
    latest = await db.scalar(select(MarketOdds.id).where(
        MarketOdds.fixture_id == fixture.id, MarketOdds.provider == odds.provider,
        MarketOdds.bookmaker == odds.bookmaker, MarketOdds.market == odds.market,
        MarketOdds.outcome == odds.outcome,
    ).order_by(MarketOdds.observed_at.desc()).limit(1))
    if latest != odds.id:
        raise HTTPException(409, detail={"code":"stale_odds_snapshot","message":"A newer odds observation exists; refresh before adding."})
    existing = (await db.scalars(select(TicketSelection).where(
        TicketSelection.ticket_id == ticket.id, TicketSelection.fixture_id == fixture.id
    ))).all()
    market_key = odds.market.casefold().replace("_", "").replace(" ", "").replace("-", "")
    for item in existing:
        if item.market.casefold().replace("_", "").replace(" ", "").replace("-", "") == market_key:
            code = "duplicate_selection" if item.outcome == odds.outcome else "contradictory_selection"
            message = "This selection already exists." if item.outcome == odds.outcome else "A conflicting outcome for this market already exists."
            raise HTTPException(409, detail={"code":code,"message":message})
    home, away = await db.get(Team, fixture.home_team_id), await db.get(Team, fixture.away_team_id)
    return payload, {
        "summary":f"Add {odds.market} / {odds.outcome} at decimal odds {Decimal(odds.decimal_odds):.2f}",
        "fixture":{"id":fixture.id,"home":home.name if home else "Unknown","away":away.name if away else "Unknown","kickoff_at":kickoff.isoformat()},
        "source":{"provider":odds.provider,"bookmaker":odds.bookmaker,"observed_at":observed.isoformat(),"market_odds_id":odds.id},
        "warnings":["Odds are snapshotted for analysis; this action does not place a wager."],
    }

@router.get("")
async def list_tickets(_: Session = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    tickets = (await db.scalars(select(Ticket).order_by(Ticket.updated_at.desc()).limit(100))).all()
    items = []
    for ticket in tickets:
        count = await db.scalar(select(func.count(TicketSelection.id)).where(TicketSelection.ticket_id == ticket.id))
        items.append({"id":ticket.id,"name":ticket.name,"status":ticket.status,"notes":ticket.notes,
                      "selection_count":int(count or 0),"updated_at":_utc(ticket.updated_at).isoformat()})
    return {"items":items}

@router.get("/{ticket_id}")
async def ticket_detail(ticket_id: str, _: Session = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(404, detail={"code":"ticket_not_found","message":"Ticket not found."})
    rows = (await db.execute(
        select(TicketSelection, Fixture, Competition.name.label("competition"), Team.name.label("home"))
        .join(Fixture, TicketSelection.fixture_id == Fixture.id)
        .join(Competition, Fixture.competition_id == Competition.id)
        .join(Team, Fixture.home_team_id == Team.id)
        .where(TicketSelection.ticket_id == ticket.id)
    )).all()
    selections = []
    combined = Decimal("1")
    for selection, fixture, competition, home_name in rows:
        away = await db.get(Team, fixture.away_team_id)
        combined *= Decimal(selection.odds_snapshot)
        selections.append({"id":selection.id,"fixture_id":fixture.id,"competition":competition,
            "home_team":home_name,"away_team":away.name if away else "Unknown",
            "match_date":fixture.match_date.isoformat() if fixture.match_date else None,
            "kickoff_at":_utc(fixture.kickoff_at).isoformat() if fixture.kickoff_at else None,
            "market":selection.market,"outcome":selection.outcome,"odds_snapshot":str(selection.odds_snapshot),
            "bookmaker":selection.bookmaker,"metadata":selection.metadata_json})
    revisions = (await db.scalars(select(TicketRevision).where(TicketRevision.ticket_id == ticket.id)
        .order_by(TicketRevision.revision.desc()).limit(50))).all()
    return {"id":ticket.id,"name":ticket.name,"status":ticket.status,"notes":ticket.notes,
        "selection_count":len(selections),"combined_decimal_odds":str(combined if selections else Decimal("0")),
        "selections":selections,"revisions":[{"revision":item.revision,"actor":item.actor,
        "before_state":item.before_state,"after_state":item.after_state,
        "created_at":_utc(item.created_at).isoformat()} for item in revisions]}

@router.get("/{ticket_id}/export.csv")
async def export_ticket_csv(ticket_id: str, _: Session = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(404, detail={"code":"ticket_not_found","message":"Ticket not found."})
    rows = (await db.execute(select(TicketSelection, Fixture, Competition.name.label("competition"),
        Team.name.label("home")).join(Fixture, TicketSelection.fixture_id == Fixture.id)
        .join(Competition, Fixture.competition_id == Competition.id).join(Team, Fixture.home_team_id == Team.id)
        .where(TicketSelection.ticket_id == ticket.id))).all()
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["ticket","status","competition","home_team","away_team","match_date","market","outcome",
                     "decimal_odds","bookmaker","source_provider","observed_at"])
    for selection, fixture, competition, home_name in rows:
        away = await db.get(Team, fixture.away_team_id)
        metadata = selection.metadata_json
        writer.writerow([_csv_safe(ticket.name),_csv_safe(ticket.status),_csv_safe(competition),
            _csv_safe(home_name),_csv_safe(away.name if away else "Unknown"),
            _csv_safe(fixture.match_date.isoformat() if fixture.match_date else None),
            _csv_safe(selection.market),_csv_safe(selection.outcome),_csv_safe(selection.odds_snapshot),
            _csv_safe(selection.bookmaker),_csv_safe(metadata.get("provider")),_csv_safe(metadata.get("observed_at"))])
    return Response(stream.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":f'attachment; filename="matchx-ticket-{ticket.id}.csv"'})

@router.post("/preview")
async def preview_action(body: PreviewBody, session: Session = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    payload, preview = await _validate_action(body.action, body.payload, db)
    now = datetime.now(timezone.utc)
    signed = {"v":1,"session_id":session.id,"action":body.action,"payload":payload,
        "request_hash":_request_hash(body.action,payload),"nonce":secrets.token_urlsafe(18),
        "expires_at":int((now + timedelta(seconds=TOKEN_TTL)).timestamp())}
    return {"action":body.action,"payload":payload,"preview":preview,"confirmation_token":_sign(signed),
        "expires_at":datetime.fromtimestamp(signed["expires_at"],timezone.utc).isoformat(),
        "confirmation_required":True}

@router.post("/confirm")
async def confirm_action(body: ConfirmBody, session: Session = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    token = _verify(body.confirmation_token)
    now = int(datetime.now(timezone.utc).timestamp())
    if token.get("v") != 1 or token.get("session_id") != session.id:
        raise HTTPException(403, detail={"code":"confirmation_session_mismatch","message":"Sign in again to confirm this action."})
    if not isinstance(token.get("expires_at"), int) or token["expires_at"] < now:
        raise HTTPException(410, detail={"code":"confirmation_expired","message":"Confirmation expired. Preview again."})
    action, payload, nonce = token.get("action"), token.get("payload"), token.get("nonce")
    if not isinstance(action,str) or not isinstance(payload,dict) or not isinstance(nonce,str):
        raise HTTPException(400, detail={"code":"invalid_confirmation_token","message":"Confirmation token payload is invalid."})
    request_hash = _request_hash(action,payload)
    if not hmac.compare_digest(str(token.get("request_hash","")),request_hash):
        raise HTTPException(400, detail={"code":"confirmation_hash_mismatch","message":"Confirmation token failed integrity validation."})
    replay = await db.get(IdempotencyKey,nonce)
    if replay:
        if replay.request_hash != request_hash:
            raise HTTPException(409, detail={"code":"idempotency_conflict","message":"Confirmation key was used for another request."})
        return replay.response_body
    payload, _ = await _validate_action(action,payload,db)
    try:
        if action == "create_ticket":
            ticket = Ticket(name=payload["name"],notes=payload.get("notes"),status="draft")
            db.add(ticket)
            await db.flush()
            after = {"name":ticket.name,"notes":ticket.notes,"status":ticket.status,"selection_count":0}
            await _revision(db,ticket.id,{},after)
            result = {"status":"confirmed","action":action,"ticket_id":ticket.id,"ticket":after}
        elif action == "add_selection":
            ticket = await db.get(Ticket,payload["ticket_id"])
            fixture = await db.get(Fixture,payload["fixture_id"])
            odds = await db.get(MarketOdds,payload["market_odds_id"])
            if ticket is None or fixture is None or odds is None or odds.fixture_id != fixture.id:
                raise HTTPException(409, detail={"code":"action_state_changed","message":"Ticket or odds changed. Preview again."})
            count = int(await db.scalar(select(func.count(TicketSelection.id)).where(TicketSelection.ticket_id == ticket.id)) or 0)
            selection = TicketSelection(ticket_id=ticket.id,fixture_id=fixture.id,market=odds.market,outcome=odds.outcome,
                odds_snapshot=Decimal(odds.decimal_odds),bookmaker=odds.bookmaker,
                metadata_json={"market_odds_id":odds.id,"provider":odds.provider,"observed_at":_utc(odds.observed_at).isoformat()})
            db.add(selection)
            await db.flush()
            await _revision(db,ticket.id,{"selection_count":count,"status":ticket.status},
                {"selection_count":count+1,"status":ticket.status,"added_selection":{"id":selection.id,
                 "fixture_id":fixture.id,"market":selection.market,"outcome":selection.outcome,
                 "odds_snapshot":str(selection.odds_snapshot)}})
            ticket.updated_at = datetime.now(timezone.utc)
            result = {"status":"confirmed","action":action,"ticket_id":ticket.id,"selection_id":selection.id,"selection_count":count+1}
        elif action == "remove_selection":
            ticket = await db.get(Ticket,payload["ticket_id"])
            selection = await db.get(TicketSelection,payload["selection_id"])
            if ticket is None or selection is None or selection.ticket_id != ticket.id:
                raise HTTPException(409, detail={"code":"action_state_changed","message":"Selection changed. Preview again."})
            count = int(await db.scalar(select(func.count(TicketSelection.id)).where(TicketSelection.ticket_id == ticket.id)) or 0)
            before = {"selection_count":count,"status":ticket.status,"removed_selection":{"id":selection.id,
                "fixture_id":selection.fixture_id,"market":selection.market,"outcome":selection.outcome,
                "odds_snapshot":str(selection.odds_snapshot)}}
            await db.delete(selection)
            await _revision(db,ticket.id,before,{"selection_count":max(0,count-1),"status":ticket.status})
            ticket.updated_at = datetime.now(timezone.utc)
            result = {"status":"confirmed","action":action,"ticket_id":ticket.id,"selection_count":max(0,count-1)}
        else:
            ticket = await db.get(Ticket,payload["ticket_id"])
            if ticket is None or ticket.status != "draft":
                raise HTTPException(409, detail={"code":"action_state_changed","message":"Ticket changed. Preview again."})
            before = {"name":ticket.name,"notes":ticket.notes,"status":ticket.status}
            ticket.status = "archived"
            ticket.updated_at = datetime.now(timezone.utc)
            await _revision(db,ticket.id,before,{"name":ticket.name,"notes":ticket.notes,"status":ticket.status})
            result = {"status":"confirmed","action":action,"ticket_id":ticket.id,"ticket":{"status":ticket.status}}
        db.add(IdempotencyKey(key=nonce,request_hash=request_hash,response_body=result))
        await db.commit()
        return result
    except IntegrityError as exc:
        await db.rollback()
        replay = await db.get(IdempotencyKey,nonce)
        if replay and replay.request_hash == request_hash:
            return replay.response_body
        raise HTTPException(409, detail={"code":"ticket_conflict","message":"Ticket changed concurrently. Preview again."}) from exc
