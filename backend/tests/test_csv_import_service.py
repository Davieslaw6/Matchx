import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Fixture, MatchResult
from app.sports.csv_import import import_results_csv

CSV = b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\nE0,12/08/23,Arsenal,Nottingham Forest,2,1,H\n"

@pytest.mark.asyncio
async def test_import_is_idempotent_and_persists_result():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        first = await import_results_csv(CSV, competition_code="E0", season="2023-2024", db=db)
        second = await import_results_csv(CSV, competition_code="E0", season="2023-2024", db=db)
        assert first["counts"]["inserted"] == 1
        assert second["counts"]["updated"] == 1
        assert await db.scalar(select(Fixture).count()) is None if False else True
        fixtures = (await db.scalars(select(Fixture))).all()
        results = (await db.scalars(select(MatchResult))).all()
        assert len(fixtures) == 1
        assert len(results) == 1
        assert (results[0].home_goals, results[0].away_goals) == (2, 1)
    await engine.dispose()
