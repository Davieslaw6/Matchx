from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, DataSyncRun, Fixture, MatchResult
from app.sports.sync import sync_provider_window

class FakeProvider:
    name = "fixture-test-provider"
    async def fixtures(self, start, end, competition_id=None):
        return []
    async def results(self, start, end, competition_id=None):
        return [{
            "provider_fixture_id": "fixture-123",
            "competition_provider_id": "league-1",
            "competition_name": "Test League",
            "season": "test-season",
            "home_team_provider_id": "team-a",
            "home_team_name": "Alpha FC",
            "away_team_provider_id": "team-b",
            "away_team_name": "Beta FC",
            "match_date": date(2025, 1, 1),
            "kickoff_at": datetime(2025, 1, 1, 15, tzinfo=timezone.utc),
            "status": "finished",
            "score": {"fullTime": {"home": 2, "away": 0}},
            "venue": None,
        }]

@pytest.mark.asyncio
async def test_provider_sync_is_idempotent(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sync.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        first = await sync_provider_window(FakeProvider(), date(2025, 1, 1), date(2025, 1, 2), db)
        second = await sync_provider_window(FakeProvider(), date(2025, 1, 1), date(2025, 1, 2), db)
        assert first["counts"]["fixtures_inserted"] == 1
        assert first["counts"]["results_inserted"] == 1
        assert second["counts"]["fixtures_updated"] == 1
        assert second["counts"]["results_updated"] == 1
        assert len((await db.scalars(select(Fixture))).all()) == 1
        assert len((await db.scalars(select(MatchResult))).all()) == 1
        assert len((await db.scalars(select(DataSyncRun))).all()) == 2
    await engine.dispose()
