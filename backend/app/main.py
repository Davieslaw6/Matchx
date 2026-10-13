import datetime as dt
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from .chat.llm import LLMError, build_llm
from .chat.orchestrator import run_chat
from .config import Settings, get_settings
from .data.ingest import ingest_matches
from .data.provider import ProviderError, ProviderRestricted
from .data.registry import PROVIDER_NAMES, build_provider, get_active_provider_name, is_configured, set_active_provider
from .db import Base, make_engine, make_session_factory, utcnow
from .engine.errors import InsufficientDataError
from .fixtures import resolve_fixture
from .models import AppSetting, Conversation, Fixture, Message, Prediction, PredictionEvaluation
from .security import require_access
from .service import NoModelError, backtest_competition, evaluate_predictions, predict_fixture, train_competition

_state: dict = {}


def get_session_factory():
    if "sf" not in _state:
        eng = make_engine(get_settings().database_url)
        if get_settings().auto_create_tables:
            Base.metadata.create_all(eng)
        _state["sf"] = make_session_factory(eng)
    return _state["sf"]


def get_session():
    s = get_session_factory()()
    try:
        yield s
    finally:
        s.close()


def get_provider(cfg: Settings = Depends(get_settings), s: Session = Depends(get_session)):
    try:
        return build_provider(get_active_provider_name(s, cfg), cfg)
    except ProviderError as e:
        raise HTTPException(503, str(e))


def get_llm(cfg: Settings = Depends(get_settings)):
    try:
        return build_llm(cfg)
    except LLMError as e:
        raise HTTPException(503, str(e))


app = FastAPI(title="footy-prediq", docs_url=None, redoc_url=None)
auth = [Depends(require_access)]


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- provider selection ----------
@app.get("/api/providers", dependencies=auth)
def providers(s: Session = Depends(get_session), cfg: Settings = Depends(get_settings)):
    active = get_active_provider_name(s, cfg)
    return {"active": active, "providers": [{"name": n, "configured": is_configured(n, cfg), "active": n == active}
                                            for n in PROVIDER_NAMES]}


class ProviderChoice(BaseModel):
    name: str


@app.put("/api/provider", dependencies=auth)
def choose_provider(c: ProviderChoice, s: Session = Depends(get_session), cfg: Settings = Depends(get_settings)):
    if c.name not in PROVIDER_NAMES:
        raise HTTPException(400, f"Unknown provider. Choose one of {PROVIDER_NAMES}")
    if not is_configured(c.name, cfg):
        raise HTTPException(400, f"{c.name} has no API key configured; add it to the environment first")
    set_active_provider(s, c.name)
    return {"active": c.name, "note": "Data, models and predictions are kept separate per provider: sync and train again after switching."}


# ---------- data ----------
class SyncRequest(BaseModel):
    competitions: list[str] | None = None
    seasons: list[int] | None = None


@app.post("/api/sync", dependencies=auth)
def sync(req: SyncRequest, s: Session = Depends(get_session), cfg: Settings = Depends(get_settings),
         provider=Depends(get_provider)):
    now = utcnow()
    cur = now.year if now.month >= 8 else now.year - 1
    seasons = req.seasons or [cur - 1, cur]
    comps = [c.upper() for c in (req.competitions or cfg.leagues)]
    bad = [c for c in comps if c not in cfg.leagues]
    if bad:
        raise HTTPException(400, f"Not enabled: {bad}")
    report = {}
    for code in comps:
        notes, new, res = [], 0, 0
        for season in seasons:
            try:
                r = ingest_matches(s, provider.name, provider.get_matches(code, season))
                new += r.fixtures_new; res += r.results_recorded
            except ProviderRestricted as e:
                notes.append(f"season {season}: not available on this API plan ({e})")
            except ProviderError as e:
                raise HTTPException(502, f"Data provider error for {code}: {e}")
        key = f"last_sync:{provider.name}:{code}"
        row = s.get(AppSetting, key)
        if row: row.value, row.updated_at = now.isoformat(), now
        else: s.add(AppSetting(key=key, value=now.isoformat(), updated_at=now))
        s.commit()
        report[code] = {"provider": provider.name, "new_fixtures": new, "results_recorded": res, "notes": notes}
    return report


@app.post("/api/train/{code}", dependencies=auth)
def train(code: str, s: Session = Depends(get_session), cfg: Settings = Depends(get_settings)):
    if code.upper() not in cfg.leagues:
        raise HTTPException(400, "Competition not enabled")
    try:
        reg = train_competition(s, cfg, code.upper(), get_active_provider_name(s, cfg))
    except InsufficientDataError as e:
        raise HTTPException(422, str(e))
    return {"version": reg.version, "provider": reg.provider, "n_matches": reg.n_matches, "as_of": reg.as_of.isoformat()}


@app.post("/api/backtest/{code}", dependencies=auth)
def run_backtest(code: str, s: Session = Depends(get_session), cfg: Settings = Depends(get_settings)):
    if code.upper() not in cfg.leagues:
        raise HTTPException(400, "Competition not enabled")
    try:
        return backtest_competition(s, cfg, code.upper(), get_active_provider_name(s, cfg))
    except InsufficientDataError as e:
        raise HTTPException(422, str(e))


class SearchQuery(BaseModel):
    home: str = Field(min_length=1, max_length=80)
    away: str = Field(min_length=1, max_length=80)
    competition: str | None = Field(default=None, max_length=10)
    on_date: dt.date | None = None


def _fx_dict(f: Fixture) -> dict:
    return {"fixture_id": f.id, "home": f.home_team.name, "away": f.away_team.name,
            "competition": f.competition.name, "kickoff_utc": f.utc_kickoff.isoformat(), "status": f.status}


@app.post("/api/fixtures/search", dependencies=auth)
def search(q: SearchQuery, s: Session = Depends(get_session), cfg: Settings = Depends(get_settings)):
    r = resolve_fixture(s, get_active_provider_name(s, cfg), q.home, q.away, q.competition, q.on_date)
    return {"status": r.status, "message": r.message, "fixtures": [_fx_dict(f) for f in r.fixtures]}


@app.post("/api/predict/{fixture_id}", dependencies=auth)
def predict(fixture_id: int, s: Session = Depends(get_session), cfg: Settings = Depends(get_settings)):
    try:
        return predict_fixture(s, cfg, fixture_id, get_active_provider_name(s, cfg))
    except NoModelError as e:
        raise HTTPException(409, str(e))
    except InsufficientDataError as e:
        raise HTTPException(422, f"Prediction declined: {e}")


@app.get("/api/predictions", dependencies=auth)
def history(limit: int = 50, s: Session = Depends(get_session)):
    limit = max(1, min(limit, 200))
    evaluate_predictions(s)
    rows = s.execute(select(Prediction, PredictionEvaluation)
                     .outerjoin(PredictionEvaluation, PredictionEvaluation.prediction_id == Prediction.id)
                     .order_by(Prediction.created_at.desc()).limit(limit)).all()
    return [{"prediction_id": p.id, "fixture_id": p.fixture_id, "model_version": p.model_version,
             "provider": p.payload.get("provider"), "created_at": p.created_at.isoformat(),
             "home_team": p.payload["home_team"], "away_team": p.payload["away_team"],
             "result": {"home": p.home_win, "draw": p.draw, "away": p.away_win},
             "evaluation": None if e is None else {"score": f"{e.home_goals}-{e.away_goals}",
                                                   "log_loss": e.log_loss, "brier": e.brier}} for p, e in rows]


# ---------- chat ----------
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None


@app.post("/api/chat", dependencies=auth)
def chat(body: ChatIn, s: Session = Depends(get_session), cfg: Settings = Depends(get_settings), llm=Depends(get_llm)):
    try:
        return run_chat(s, cfg, llm, get_active_provider_name(s, cfg), body.message, body.conversation_id)
    except KeyError:
        raise HTTPException(404, "Conversation not found")
    except LLMError as e:
        raise HTTPException(502, f"AI provider unavailable: {e}. No answer was generated.")


@app.get("/api/conversations/{cid}/export", dependencies=auth)
def export_conversation(cid: int, s: Session = Depends(get_session)):
    c = s.get(Conversation, cid)
    if not c:
        raise HTTPException(404, "Conversation not found")
    return {"conversation_id": c.id, "created_at": c.created_at.isoformat(),
            "messages": [{"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()} for m in c.messages]}


@app.delete("/api/conversations/{cid}", dependencies=auth)
def delete_conversation(cid: int, s: Session = Depends(get_session)):
    c = s.get(Conversation, cid)
    if not c:
        raise HTTPException(404, "Conversation not found")
    s.delete(c); s.commit()
    return {"deleted": cid}


@app.delete("/api/conversations", dependencies=auth)
def delete_all_conversations(s: Session = Depends(get_session)):
    s.execute(delete(Message)); s.execute(delete(Conversation)); s.commit()
    return {"deleted": "all"}
