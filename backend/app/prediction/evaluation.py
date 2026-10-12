"""Evaluate only stored pre-kickoff predictions after verified results arrive."""
import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Fixture, MatchResult, Prediction, PredictionEvaluation

OUTCOMES = ("home_win", "draw", "away_win")

async def evaluate_finished_predictions(db: AsyncSession, *, limit: int = 500) -> dict[str, Any]:
    rows = (await db.execute(
        select(Prediction, Fixture, MatchResult)
        .join(Fixture, Prediction.fixture_id == Fixture.id)
        .join(MatchResult, MatchResult.fixture_id == Fixture.id)
        .where(Fixture.status == "finished", Fixture.kickoff_at.is_not(None),
               Prediction.status.in_(("live", "superseded")),
               Prediction.data_cutoff_at < Fixture.kickoff_at,
               Prediction.created_at < Fixture.kickoff_at)
        .order_by(Fixture.kickoff_at.desc(), Prediction.created_at.desc())
        .limit(max(limit * 5, limit))
    )).all()
    existing_ids = set((await db.scalars(select(PredictionEvaluation.prediction_id))).all())
    evaluated: list[dict[str, Any]] = []
    skipped = 0
    for prediction, fixture, result in rows:
        if prediction.id in existing_ids:
            continue
        if len(evaluated) >= limit:
            break
        raw = prediction.probabilities
        try:
            probs = {name: float(raw[name]) for name in OUTCOMES}
        except (KeyError, TypeError, ValueError):
            skipped += 1
            continue
        if any(not math.isfinite(value) or value < 0 or value > 1 for value in probs.values()):
            skipped += 1
            continue
        if abs(sum(probs.values()) - 1.0) > 1e-3:
            skipped += 1
            continue
        actual = "home_win" if result.home_goals > result.away_goals else "draw" if result.home_goals == result.away_goals else "away_win"
        brier = sum((probs[name] - float(name == actual)) ** 2 for name in OUTCOMES) / 3.0
        actual_probability = probs[actual]
        log_loss = -math.log(max(actual_probability, 1e-15))
        predicted = max(OUTCOMES, key=lambda name: probs[name])
        metrics = {
            "actual_outcome": actual, "predicted_outcome": predicted,
            "probabilities": probs, "brier_score": brier, "log_loss": log_loss,
            "top_outcome_correct": predicted == actual,
            "result": {"home_goals": result.home_goals, "away_goals": result.away_goals},
            "kickoff_at": fixture.kickoff_at.isoformat(),
            "data_cutoff_at": prediction.data_cutoff_at.isoformat(),
            "model_version": prediction.model_version,
            "probability_floor_used": actual_probability < 1e-15,
        }
        db.add(PredictionEvaluation(prediction_id=prediction.id, metrics=metrics))
        existing_ids.add(prediction.id)
        evaluated.append(metrics)
    await db.flush()
    count = len(evaluated)
    return {
        "evaluated": count, "skipped_invalid_probabilities": skipped,
        "mean_brier_score": sum(item["brier_score"] for item in evaluated) / count if count else None,
        "mean_log_loss": sum(item["log_loss"] for item in evaluated) / count if count else None,
        "top_outcome_accuracy": sum(item["top_outcome_correct"] for item in evaluated) / count if count else None,
        "method": "multiclass 1X2; Brier is mean squared error across three outcomes; log loss uses 1e-15 floor",
    }
