from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Competition, Fixture, MatchResult, Prediction, PredictionEvaluation, Team
from app.prediction.evaluation import evaluate_finished_predictions

@pytest.mark.asyncio
async def test_evaluation_uses_only_pre_kickoff_predictions_and_is_idempotent(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'evaluation.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    kickoff = now - timedelta(days=1)
    async with factory() as db:
        home = Team(provider="test", provider_team_id="home", name="Home")
        away = Team(provider="test", provider_team_id="away", name="Away")
        competition = Competition(provider="test", provider_competition_id="league", name="League")
        db.add_all([home, away, competition])
        await db.flush()
        fixture = Fixture(provider="test", provider_fixture_id="finished-1",
            competition_id=competition.id, home_team_id=home.id, away_team_id=away.id,
            match_date=date.today() - timedelta(days=1), kickoff_at=kickoff, status="finished")
        db.add(fixture)
        await db.flush()
        db.add(MatchResult(fixture_id=fixture.id, home_goals=2, away_goals=1, source="test"))
        db.add(Prediction(fixture_id=fixture.id, model_version="test-v1",
            data_cutoff_at=kickoff - timedelta(days=3), created_at=kickoff - timedelta(days=2),
            probabilities={"home_win":0.6,"draw":0.25,"away_win":0.15}, feature_snapshot={}, status="live"))
        await db.commit()

        first = await evaluate_finished_predictions(db, limit=100)
        await db.commit()
        second = await evaluate_finished_predictions(db, limit=100)
        await db.commit()
        assert first["evaluated"] == 1
        assert first["top_outcome_accuracy"] == 1.0
        assert first["mean_brier_score"] == pytest.approx(0.0816666667)
        assert second["evaluated"] == 0
        assert await db.scalar(select(func.count(PredictionEvaluation.id))) == 1
    await engine.dispose()

@pytest.mark.asyncio
async def test_prediction_with_cutoff_at_or_after_kickoff_is_not_evaluated(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'leakage.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    kickoff = now - timedelta(days=1)
    async with factory() as db:
        home = Team(provider="test", provider_team_id="home", name="Home")
        away = Team(provider="test", provider_team_id="away", name="Away")
        competition = Competition(provider="test", provider_competition_id="league", name="League")
        db.add_all([home, away, competition])
        await db.flush()
        fixture = Fixture(provider="test", provider_fixture_id="finished-2",
            competition_id=competition.id, home_team_id=home.id, away_team_id=away.id,
            match_date=date.today() - timedelta(days=1), kickoff_at=kickoff, status="finished")
        db.add(fixture)
        await db.flush()
        db.add(MatchResult(fixture_id=fixture.id, home_goals=0, away_goals=0, source="test"))
        db.add(Prediction(fixture_id=fixture.id, model_version="leaky-v1",
            data_cutoff_at=kickoff, created_at=kickoff - timedelta(hours=1),
            probabilities={"home_win":0.3,"draw":0.4,"away_win":0.3}, feature_snapshot={}, status="live"))
        await db.commit()
        result = await evaluate_finished_predictions(db, limit=100)
        assert result["evaluated"] == 0
        assert await db.scalar(select(func.count(PredictionEvaluation.id))) == 0
    await engine.dispose()
