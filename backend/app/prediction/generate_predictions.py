"""Train one competition-specific model and persist predictions before kickoff."""
import argparse
import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db import SessionLocal
from app.models import DataSyncRun, Fixture, ModelRegistry, Prediction, Team
from app.prediction.backtest_cli import load_observations
from app.prediction.dixon_coles import ModelFitError, fit_dixon_coles, select_time_decay
from app.prediction.poisson import derive_markets

def _training_hash(observations) -> str:
    canonical = [{
        "home_team": item.home_team, "away_team": item.away_team,
        "home_goals": item.home_goals, "away_goals": item.away_goals,
        "played_at": item.played_at.isoformat(),
    } for item in observations]
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

async def generate_for_competition(db: AsyncSession, competition_id: str,
                                   cutoff: datetime | None = None) -> dict[str, Any]:
    cutoff = cutoff or datetime.now(timezone.utc)
    if cutoff.tzinfo is None:
        raise ValueError("cutoff must be timezone-aware")
    cutoff = cutoff.astimezone(timezone.utc)
    run = DataSyncRun(job_name="prediction_generation", provider="internal", status="running",
                      counts={"competition_id": competition_id, "generated": 0, "skipped": 0})
    db.add(run)
    await db.flush()
    try:
        observations = await load_observations(db, competition_id)
        training = [item for item in observations if item.played_at.astimezone(timezone.utc) < cutoff]
        if len(training) < 65:
            raise ModelFitError(f"Insufficient data: need at least 65 completed pre-cutoff matches; found {len(training)}.")
        selection = select_time_decay(training, data_cutoff=cutoff,
                                      candidates=(90.0, 180.0, 365.0, 730.0),
                                      folds=3, min_training_matches=50)
        model = fit_dixon_coles(training, data_cutoff=cutoff,
                                time_decay_days=selection.best_days, min_matches=50)
        data_hash = _training_hash(training)
        model_version = f"dc-{data_hash[:12]}-{cutoff.strftime('%Y%m%dT%H%M%SZ')}"
        registry = await db.scalar(select(ModelRegistry).where(ModelRegistry.version == model_version))
        if registry is None:
            registry = ModelRegistry(
                version=model_version,
                model_type="dixon_coles_m1",
                hyperparameters={
                    "time_decay_days": selection.best_days,
                    "time_decay_validation_log_loss": selection.mean_log_loss_by_days,
                    "l2_penalty": 0.01,
                    "training_cutoff": cutoff.isoformat(),
                },
                data_hash=data_hash,
                git_sha=os.getenv("GITHUB_SHA"),
                metrics={
                    "training_matches": model.training_matches,
                    "weighted_log_likelihood": model.weighted_log_likelihood,
                    "optimizer_message": model.optimizer_message,
                    "out_of_sample_evaluation": "not_run_by_generation_job",
                },
            )
            db.add(registry)
            await db.flush()

        home = aliased(Team)
        away = aliased(Team)
        upcoming = (await db.execute(
            select(Fixture, home.name.label("home_name"), away.name.label("away_name"))
            .join(home, Fixture.home_team_id == home.id)
            .join(away, Fixture.away_team_id == away.id)
            .where(Fixture.competition_id == competition_id,
                   Fixture.status == "scheduled", Fixture.kickoff_at.is_not(None),
                   Fixture.kickoff_at > cutoff)
            .order_by(Fixture.kickoff_at.asc())
        )).all()
        counts = {"competition_id": competition_id, "generated": 0, "skipped": 0,
                  "upcoming_fixtures": len(upcoming), "training_matches": model.training_matches}
        for fixture, home_name, away_name in upcoming:
            if home_name not in model.attack_strength or away_name not in model.attack_strength:
                counts["skipped"] += 1
                continue
            existing_same = await db.scalar(select(Prediction.id).where(
                Prediction.fixture_id == fixture.id, Prediction.model_version == model_version
            ).limit(1))
            if existing_same:
                counts["skipped"] += 1
                continue
            try:
                home_xg, away_xg = model.expected_goals(home_name, away_name)
                grid = model.scoreline_grid(home_name, away_name)
                markets = derive_markets(grid, top_n=5)
            except (ModelFitError, ValueError):
                counts["skipped"] += 1
                continue
            previous = await db.scalar(select(Prediction).where(
                Prediction.fixture_id == fixture.id, Prediction.status == "live"
            ).order_by(Prediction.created_at.desc()).limit(1))
            if previous:
                previous.status = "superseded"
            prediction = Prediction(
                fixture_id=fixture.id,
                model_version=model_version,
                data_cutoff_at=cutoff,
                probabilities={
                    "home_win": markets.home_win,
                    "draw": markets.draw,
                    "away_win": markets.away_win,
                    "over": {str(line): probability for line, probability in markets.over.items()},
                    "btts_yes": markets.btts_yes,
                    "btts_no": markets.btts_no,
                    "correct_scores": [
                        {"home_goals": home_goals, "away_goals": away_goals, "probability": probability}
                        for home_goals, away_goals, probability in markets.correct_scores
                    ],
                },
                feature_snapshot={
                    "home_xg": home_xg,
                    "away_xg": away_xg,
                    "rho": model.rho,
                    "home_advantage": model.home_advantage,
                    "time_decay_days": model.time_decay_days,
                    "training_matches": model.training_matches,
                    "data_hash": data_hash,
                    "data_cutoff": cutoff.isoformat(),
                    "retained_scoreline_mass": grid.retained_mass,
                },
                supersedes_id=previous.id if previous else None,
                status="live",
            )
            db.add(prediction)
            counts["generated"] += 1
        run.status = "succeeded"
        run.counts = counts
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": run.status, "model_version": model_version, "data_hash": data_hash, "counts": counts}
    except Exception as exc:
        await db.rollback()
        failed = DataSyncRun(job_name="prediction_generation", provider="internal", status="failed",
            counts={"competition_id": competition_id}, error_summary=type(exc).__name__,
            started_at=cutoff, finished_at=datetime.now(timezone.utc))
        db.add(failed)
        await db.commit()
        raise

async def _run(competition_id: str) -> None:
    async with SessionLocal() as db:
        result = await generate_for_competition(db, competition_id)
    print(json.dumps(result, indent=2))

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate pre-kickoff MATCH X predictions for one competition.")
    parser.add_argument("--competition-id", required=True, help="Internal competition UUID.")
    args = parser.parse_args()
    asyncio.run(_run(args.competition_id))

if __name__ == "__main__":
    main()
