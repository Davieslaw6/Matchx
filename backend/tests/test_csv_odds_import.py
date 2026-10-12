import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, MarketOdds
from app.sports.csv_import import import_results_csv

CSV = (
    b"Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A\n"
    b"E0,12/08/25,15:00,Arsenal,Forest,2,1,H,1.80,3.60,4.50\n"
)

@pytest.mark.asyncio
async def test_csv_import_upserts_odds_snapshots_idempotently(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'odds-import.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        first = await import_results_csv(CSV, competition_code="E0", season="2025-2026", db=db)
        second = await import_results_csv(CSV, competition_code="E0", season="2025-2026", db=db)
        assert first["counts"]["odds_inserted"] == 3
        assert second["counts"]["odds_updated"] == 3
        assert second["counts"]["odds_inserted"] == 0
        assert await db.scalar(select(func.count(MarketOdds.id))) == 3
        rows = (await db.scalars(select(MarketOdds))).all()
        assert all(row.observed_at_precision == "closing_at_kickoff" for row in rows)
        assert {row.outcome for row in rows} == {"home", "draw", "away"}
    await engine.dispose()
