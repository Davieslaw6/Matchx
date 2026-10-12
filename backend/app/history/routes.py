"""Authenticated prediction history and idempotent post-match evaluation."""
import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.auth import require_csrf, require_owner
from app.db import get_db
from app.models import (
    Competition, Fixture, IdempotencyKey, MatchResult, Prediction,
    PredictionEvaluation, Session, Team,
)
from app.prediction.evaluation import evaluate_finished_predictions

router = APIRouter(prefix="/api/v1/history", tags=["prediction-history"])

class EvaluateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=500, ge=1, le=500)

def _hash_request(limit: int) -> str:
    return hashlib.sha256(json.dumps({"action":"evaluate_predictions","limit":limit},
        sort_keys=True,separators=(",",":")).encode()).hexdigest()

@router.get("")
async def prediction_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: Session = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    home, away = aliased(Team), aliased(Team)
    query = (select(Prediction, Fixture, Competition.name.label("competition"),
                    home.name.label("home"), away.name.label("away"),
                    MatchResult, PredictionEvaluation)
        .join(Fixture, Prediction.fixture_id == Fixture.id)
        .join(Competition, Fixture.competition_id == Competition.id)
        .join(home, Fixture.home_team_id == home.id)
        .join(away, Fixture.away_team_id == away.id)
        .outerjoin(MatchResult, MatchResult.fixture_id == Fixture.id)
        .outerjoin(PredictionEvaluation, PredictionEvaluation.prediction_id == Prediction.id))
    total = int(await db.scalar(select(func.count(Prediction.id))) or 0)
    rows = (await db.execute(query.order_by(Fixture.kickoff_at.desc().nulls_last(),
        Prediction.created_at.desc()).offset((page - 1) * page_size).limit(page_size))).all()
    items = []
    for prediction, fixture, competition, home_name, away_name, result, evaluation in rows:
        items.append({
            "prediction_id":prediction.id, "fixture_id":fixture.id,
            "competition":competition, "home_team":home_name, "away_team":away_name,
            "kickoff_at":fixture.kickoff_at.isoformat() if fixture.kickoff_at else None,
            "match_date":fixture.match_date.isoformat() if fixture.match_date else None,
            "fixture_status":fixture.status, "prediction_status":prediction.status,
            "model_version":prediction.model_version,
            "data_cutoff_at":prediction.data_cutoff_at.isoformat(),
            "created_at":prediction.created_at.isoformat(),
            "probabilities":prediction.probabilities,
            "result":({"home_goals":result.home_goals,"away_goals":result.away_goals} if result else None),
            "evaluation":evaluation.metrics if evaluation else None,
        })
    evaluations = (await db.scalars(select(PredictionEvaluation.metrics))).all()
    valid = [item for item in evaluations if item.get("status") != "invalid_probability_snapshot"
             and isinstance(item.get("brier_score"), (int, float))
             and isinstance(item.get("log_loss"), (int, float))]
    n = len(valid)
    summary = {
        "evaluated_predictions":n,
        "mean_brier_score":sum(float(item["brier_score"]) for item in valid) / n if n else None,
        "mean_log_loss":sum(float(item["log_loss"]) for item in valid) / n if n else None,
        "top_outcome_accuracy":sum(bool(item.get("top_outcome_correct")) for item in valid) / n if n else None,
    }
    return {"items":items,"page":page,"page_size":page_size,"total":total,"summary":summary}

@router.post("/evaluate")
async def evaluate_history(
    body: EvaluateBody,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=16, max_length=160),
    _: Session = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
):
    request_hash = _hash_request(body.limit)
    existing = await db.get(IdempotencyKey,idempotency_key)
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(409, detail={"code":"idempotency_conflict","message":"Idempotency-Key was already used for a different request."})
        return existing.response_body
    result = await evaluate_finished_predictions(db,limit=body.limit)
    response_body = {"status":"completed","result":result}
    db.add(IdempotencyKey(key=idempotency_key,request_hash=request_hash,response_body=response_body))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        replay = await db.get(IdempotencyKey,idempotency_key)
        if replay and replay.request_hash == request_hash:
            return replay.response_body
        raise HTTPException(409, detail={"code":"evaluation_conflict","message":"Evaluation conflicted with another request."}) from exc
    return response_body
