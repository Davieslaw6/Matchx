"""Persist normalized provider fixtures/results with an auditable sync run."""
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Competition, DataSyncRun, Fixture, MatchResult, Team
from app.sports.provider import SportsDataProvider

async def sync_provider_window(provider: SportsDataProvider, start: date, end: date,
                               db: AsyncSession, competition_code: str | None = None) -> dict[str, Any]:
    if end < start:
        raise ValueError("end date must not precede start date")
    started = datetime.now(timezone.utc)
    counts: dict[str, int] = {
        "fixtures_received": 0, "fixtures_inserted": 0, "fixtures_updated": 0,
        "results_inserted": 0, "results_updated": 0, "invalid_scores": 0,
    }
    try:
        fixtures = await provider.fixtures(start, end, competition_code)
        results = await provider.results(start, end, competition_code)
        incoming = {record["provider_fixture_id"]: record for record in fixtures + results}
        counts["fixtures_received"] = len(incoming)
        for record in incoming.values():
            if not record.get("provider_fixture_id") or not record.get("competition_provider_id"):
                raise ValueError("Provider fixture lacks stable identity fields.")
            if not record.get("home_team_provider_id") or not record.get("away_team_provider_id"):
                raise ValueError("Provider fixture lacks stable team identities.")
            competition = await db.scalar(select(Competition).where(
                Competition.provider == provider.name,
                Competition.provider_competition_id == str(record["competition_provider_id"]),
            ))
            if not competition:
                competition = Competition(provider=provider.name,
                    provider_competition_id=str(record["competition_provider_id"]),
                    name=record.get("competition_name") or str(record["competition_provider_id"]),
                    season=record.get("season"))
                db.add(competition)
                await db.flush()
            else:
                if record.get("competition_name"):
                    competition.name = record["competition_name"]

            team_ids: dict[str, str] = {}
            for side in ("home", "away"):
                external_id = str(record[f"{side}_team_provider_id"])
                team = await db.scalar(select(Team).where(
                    Team.provider == provider.name, Team.provider_team_id == external_id
                ))
                if not team:
                    name = record.get(f"{side}_team_name")
                    if not name:
                        raise ValueError(f"Provider fixture lacks {side} team name.")
                    team = Team(provider=provider.name, provider_team_id=external_id, name=name)
                    db.add(team)
                    await db.flush()
                elif record.get(f"{side}_team_name"):
                    team.name = record[f"{side}_team_name"]
                team_ids[side] = team.id

            fixture = await db.scalar(select(Fixture).where(
                Fixture.provider == provider.name,
                Fixture.provider_fixture_id == str(record["provider_fixture_id"]),
            ))
            if fixture:
                counts["fixtures_updated"] += 1
            else:
                fixture = Fixture(provider=provider.name,
                    provider_fixture_id=str(record["provider_fixture_id"]),
                    competition_id=competition.id, home_team_id=team_ids["home"],
                    away_team_id=team_ids["away"], status="scheduled")
                db.add(fixture)
                await db.flush()
                counts["fixtures_inserted"] += 1
            fixture.competition_id = competition.id
            fixture.home_team_id = team_ids["home"]
            fixture.away_team_id = team_ids["away"]
            fixture.match_date = record.get("match_date")
            fixture.kickoff_at = record.get("kickoff_at")
            fixture.status = record.get("status") or "scheduled"
            fixture.season = record.get("season")
            fixture.venue = record.get("venue")

            full_time = (record.get("score") or {}).get("fullTime") or {}
            home_goals, away_goals = full_time.get("home"), full_time.get("away")
            if fixture.status == "finished":
                if (isinstance(home_goals, int) and not isinstance(home_goals, bool)
                    and isinstance(away_goals, int) and not isinstance(away_goals, bool)
                    and home_goals >= 0 and away_goals >= 0):
                    result = await db.scalar(select(MatchResult).where(MatchResult.fixture_id == fixture.id))
                    if result:
                        counts["results_updated"] += 1
                        result.home_goals, result.away_goals = home_goals, away_goals
                        result.source = provider.name
                    else:
                        counts["results_inserted"] += 1
                        db.add(MatchResult(fixture_id=fixture.id, home_goals=home_goals,
                                           away_goals=away_goals, source=provider.name))
                else:
                    counts["invalid_scores"] += 1
        run = DataSyncRun(job_name="fixture_sync", provider=provider.name, status="succeeded",
            counts=counts, started_at=started, finished_at=datetime.now(timezone.utc))
        db.add(run)
        await db.commit()
        return {"run_id": run.id, "status": run.status, "counts": counts}
    except Exception as exc:
        await db.rollback()
        run = DataSyncRun(job_name="fixture_sync", provider=provider.name, status="failed",
            counts=counts, error_summary=type(exc).__name__, started_at=started,
            finished_at=datetime.now(timezone.utc))
        db.add(run)
        await db.commit()
        raise
