"""CLI import for locally downloaded football-data.co.uk result CSV files."""
import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.models import Competition, DataSyncRun, Fixture, MatchResult, Team
from app.sports.football_data_csv import parse_results_csv
from app.sports.team_resolver import normalize_team_name

def _team_provider_id(name: str) -> str:
    return normalize_team_name(name).replace(" ", "-")

async def _get_or_create_team(db: AsyncSession, name: str) -> Team:
    provider_id = _team_provider_id(name)
    team = await db.scalar(select(Team).where(
        Team.provider == "football-data.co.uk", Team.provider_team_id == provider_id
    ))
    if team:
        return team
    team = Team(provider="football-data.co.uk", provider_team_id=provider_id, name=name)
    db.add(team)
    await db.flush()
    return team

async def import_results_csv(content: bytes, *, competition_code: str | None = None,
                             season: str | None = None, filename: str = "uploaded.csv",
                             db: AsyncSession) -> dict[str, Any]:
    run = DataSyncRun(job_name="csv_result_import", provider="football-data.co.uk",
                      status="running", counts={"rows_read": 0, "inserted": 0,
                      "updated": 0, "duplicates": 0, "rejected": 0})
    db.add(run)
    await db.flush()
    try:
        records = parse_results_csv(content, competition_code=competition_code)
        counts = dict(run.counts)
        counts["rows_read"] = len(records)
        for record in records:
            competition_id = record["competition_code"]
            competition = await db.scalar(select(Competition).where(
                Competition.provider == "football-data.co.uk",
                Competition.provider_competition_id == competition_id,
                Competition.season == season,
            ))
            if not competition:
                competition = Competition(provider="football-data.co.uk",
                    provider_competition_id=competition_id, name=competition_id,
                    season=season, country=None)
                db.add(competition)
                await db.flush()
            home = await _get_or_create_team(db, record["home_team_name"])
            away = await _get_or_create_team(db, record["away_team_name"])
            fixture = await db.scalar(select(Fixture).where(
                Fixture.provider == record["provider"],
                Fixture.provider_fixture_id == record["provider_fixture_id"],
            ))
            if fixture:
                counts["updated"] += 1
                fixture.competition_id = competition.id
                fixture.home_team_id = home.id
                fixture.away_team_id = away.id
                fixture.kickoff_at = record["kickoff_at"]
                fixture.status = "finished"
                fixture.season = season
            else:
                # Conservative canonical deduplication is only possible when exact kickoff
                # timestamps are known and team IDs have already been resolved identically.
                canonical = None
                if record["kickoff_at"] is not None:
                    from datetime import timedelta
                    canonical = await db.scalar(select(Fixture).where(
                        Fixture.competition_id == competition.id,
                        Fixture.home_team_id == home.id,
                        Fixture.away_team_id == away.id,
                        Fixture.kickoff_at.between(
                            record["kickoff_at"] - timedelta(minutes=30),
                            record["kickoff_at"] + timedelta(minutes=30),
                        ),
                    ).limit(1))
                if canonical:
                    counts["duplicates"] += 1
                    continue
                fixture = Fixture(provider=record["provider"],
                    provider_fixture_id=record["provider_fixture_id"],
                    competition_id=competition.id, home_team_id=home.id, away_team_id=away.id,
                    kickoff_at=record["kickoff_at"], status="finished", season=season)
                db.add(fixture)
                await db.flush()
                counts["inserted"] += 1
            result = await db.scalar(select(MatchResult).where(MatchResult.fixture_id == fixture.id))
            if result:
                result.home_goals = record["home_goals"]
                result.away_goals = record["away_goals"]
                result.source = "football-data.co.uk"
            else:
                db.add(MatchResult(fixture_id=fixture.id, home_goals=record["home_goals"],
                    away_goals=record["away_goals"], source="football-data.co.uk"))
        run.counts = counts
        run.status = "succeeded"
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()
        return {"run_id": run.id, "status": run.status, "counts": counts}
    except Exception as exc:
        await db.rollback()
        failed = DataSyncRun(job_name="csv_result_import", provider="football-data.co.uk",
            status="failed", counts={"filename": Path(filename).name}, error_summary=type(exc).__name__,
            started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc))
        db.add(failed)
        await db.commit()
        raise

async def _run_cli(path: Path, competition_code: str | None, season: str | None) -> None:
    content = path.read_bytes()
    async with SessionLocal() as db:
        result = await import_results_csv(content, competition_code=competition_code,
                                          season=season, filename=path.name, db=db)
    print(result)

def main() -> None:
    parser = argparse.ArgumentParser(description="Import football-data.co.uk historical results CSV.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--competition-code")
    parser.add_argument("--season", help="Season label for provenance, e.g. 2025-2026.")
    args = parser.parse_args()
    if not args.path.is_file():
        raise SystemExit("CSV path does not exist or is not a file.")
    asyncio.run(_run_cli(args.path, args.competition_code, args.season))

if __name__ == "__main__":
    main()
