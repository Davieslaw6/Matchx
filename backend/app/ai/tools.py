"""Allowlisted, schema-validated, read-only tools for grounded MATCH X answers."""
import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Competition, Fixture, MatchResult, Prediction, Team, TeamAlias
from app.sports.team_resolver import TeamResolver

class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

class SearchFixturesArgs(StrictArgs):
    query: str | None = Field(default=None, max_length=100)
    start_date: date | None = None
    end_date: date | None = None
    status: Literal["scheduled", "live", "finished", "postponed", "abandoned", "cancelled"] | None = None
    limit: int = Field(default=5, ge=1, le=10)

class ResolveTeamArgs(StrictArgs):
    query: str = Field(min_length=1, max_length=100)

class FixtureAnalysisArgs(StrictArgs):
    fixture_id: str = Field(min_length=1, max_length=36)

class TeamFormArgs(StrictArgs):
    team_id: str = Field(min_length=1, max_length=36)
    limit: int = Field(default=5, ge=1, le=10)

class HeadToHeadArgs(StrictArgs):
    home_team_id: str = Field(min_length=1, max_length=36)
    away_team_id: str = Field(min_length=1, max_length=36)
    limit: int = Field(default=10, ge=1, le=20)

@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    arguments: type[StrictArgs]
    handler: Any

    def model_schema(self) -> dict[str, Any]:
        return {"type": "function", "name": self.name, "description": self.description,
                "parameters": self.arguments.model_json_schema(), "strict": False}

async def _search_fixtures(args: SearchFixturesArgs, db: AsyncSession) -> dict[str, Any]:
    if args.start_date and args.end_date and args.end_date < args.start_date:
        return {"status": "invalid_date_range", "source": "database", "fixtures": []}
    home, away = aliased(Team), aliased(Team)
    query = (select(Fixture, Competition.name.label("competition"), home.name.label("home"),
                    away.name.label("away"))
             .join(Competition, Fixture.competition_id == Competition.id)
             .join(home, Fixture.home_team_id == home.id)
             .join(away, Fixture.away_team_id == away.id))
    if args.start_date:
        query = query.where(Fixture.match_date >= args.start_date)
    if args.end_date:
        query = query.where(Fixture.match_date <= args.end_date)
    if args.status:
        query = query.where(Fixture.status == args.status)
    if args.query:
        pattern = f"%{args.query.strip()}%"
        query = query.where(or_(home.name.ilike(pattern), away.name.ilike(pattern),
                                Competition.name.ilike(pattern)))
    rows = (await db.execute(query.order_by(Fixture.kickoff_at.asc().nulls_last(),
                                            Fixture.match_date.asc().nulls_last())
                             .limit(args.limit))).all()
    return {"status": "ok" if rows else "no_results", "source": "MATCH X database",
            "count": len(rows), "fixtures": [{
                "fixture_id": fixture.id, "competition": competition, "home_team": home_name,
                "away_team": away_name, "match_date": fixture.match_date.isoformat() if fixture.match_date else None,
                "kickoff_at": fixture.kickoff_at.isoformat() if fixture.kickoff_at else None,
                "status": fixture.status,
            } for fixture, competition, home_name, away_name in rows]}

async def _resolve_team(args: ResolveTeamArgs, db: AsyncSession) -> dict[str, Any]:
    teams = (await db.scalars(select(Team))).all()
    aliases = (await db.execute(select(TeamAlias.alias, TeamAlias.team_id))).all()
    resolver = TeamResolver([(team.id, team.name) for team in teams],
                             {alias: team_id for alias, team_id in aliases})
    result = resolver.resolve(args.query)
    return {"status": result.status, "source": "MATCH X database",
            "query": args.query, "team_id": result.team_id,
            "candidates": [{"team_id": candidate.team_id, "name": candidate.name,
                            "score": candidate.score} for candidate in result.candidates[:5]]}

async def _fixture_analysis(args: FixtureAnalysisArgs, db: AsyncSession) -> dict[str, Any]:
    home, away = aliased(Team), aliased(Team)
    row = (await db.execute(
        select(Fixture, Competition.name.label("competition"), home.name.label("home"),
               away.name.label("away"))
        .join(Competition, Fixture.competition_id == Competition.id)
        .join(home, Fixture.home_team_id == home.id)
        .join(away, Fixture.away_team_id == away.id)
        .where(Fixture.id == args.fixture_id)
    )).first()
    if row is None:
        return {"status": "not_found", "source": "MATCH X database", "fixture_id": args.fixture_id}
    fixture, competition, home_name, away_name = row
    prediction = await db.scalar(select(Prediction).where(
        Prediction.fixture_id == fixture.id, Prediction.status == "live"
    ).order_by(Prediction.created_at.desc()).limit(1))
    result = await db.scalar(select(MatchResult).where(MatchResult.fixture_id == fixture.id))
    return {
        "status": "ok", "source": "MATCH X database", "fixture_id": fixture.id,
        "competition": competition, "home_team": home_name, "away_team": away_name,
        "match_date": fixture.match_date.isoformat() if fixture.match_date else None,
        "kickoff_at": fixture.kickoff_at.isoformat() if fixture.kickoff_at else None,
        "match_status": fixture.status,
        "result": ({"home_goals": result.home_goals, "away_goals": result.away_goals}
                   if result else None),
        "prediction": ({
            "model_version": prediction.model_version,
            "data_cutoff_at": prediction.data_cutoff_at.isoformat(),
            "probabilities": prediction.probabilities,
            "features": prediction.feature_snapshot,
        } if prediction else None),
        "limitations": [] if prediction else ["No stored prediction is available for this fixture."],
    }

async def _team_form(args: TeamFormArgs, db: AsyncSession) -> dict[str, Any]:
    team = await db.get(Team, args.team_id)
    if team is None:
        return {"status": "not_found", "source": "MATCH X database", "team_id": args.team_id}
    home, away = aliased(Team), aliased(Team)
    rows = (await db.execute(
        select(Fixture, MatchResult, home.name.label("home"), away.name.label("away"))
        .join(MatchResult, MatchResult.fixture_id == Fixture.id)
        .join(home, Fixture.home_team_id == home.id)
        .join(away, Fixture.away_team_id == away.id)
        .where(or_(Fixture.home_team_id == team.id, Fixture.away_team_id == team.id))
        .order_by(Fixture.kickoff_at.desc().nulls_last(), Fixture.match_date.desc().nulls_last())
        .limit(args.limit)
    )).all()
    matches = []
    wins = draws = losses = goals_for = goals_against = 0
    for fixture, result, home_name, away_name in rows:
        is_home = fixture.home_team_id == team.id
        gf = result.home_goals if is_home else result.away_goals
        ga = result.away_goals if is_home else result.home_goals
        goals_for += gf
        goals_against += ga
        outcome = "W" if gf > ga else "D" if gf == ga else "L"
        wins += outcome == "W"
        draws += outcome == "D"
        losses += outcome == "L"
        matches.append({"fixture_id": fixture.id, "opponent": away_name if is_home else home_name,
                        "venue": "home" if is_home else "away", "match_date": fixture.match_date.isoformat() if fixture.match_date else None,
                        "goals_for": gf, "goals_against": ga, "outcome": outcome})
    return {"status": "ok" if matches else "insufficient_data", "source": "MATCH X database",
            "team_id": team.id, "team": team.name, "sample_size": len(matches),
            "record": {"wins": int(wins), "draws": int(draws), "losses": int(losses),
                       "goals_for": goals_for, "goals_against": goals_against},
            "matches": matches}

async def _head_to_head(args: HeadToHeadArgs, db: AsyncSession) -> dict[str, Any]:
    home_team, away_team = await db.get(Team, args.home_team_id), await db.get(Team, args.away_team_id)
    if home_team is None or away_team is None or home_team.id == away_team.id:
        return {"status": "invalid_teams", "source": "MATCH X database", "matches": []}
    rows = (await db.execute(
        select(Fixture, MatchResult)
        .join(MatchResult, MatchResult.fixture_id == Fixture.id)
        .where(or_(
            (Fixture.home_team_id == home_team.id) & (Fixture.away_team_id == away_team.id),
            (Fixture.home_team_id == away_team.id) & (Fixture.away_team_id == home_team.id),
        ))
        .order_by(Fixture.kickoff_at.desc().nulls_last(), Fixture.match_date.desc().nulls_last())
        .limit(args.limit)
    )).all()
    return {"status": "ok" if rows else "insufficient_data", "source": "MATCH X database",
            "home_team": home_team.name, "away_team": away_team.name, "sample_size": len(rows),
            "matches": [{"fixture_id": fixture.id, "match_date": fixture.match_date.isoformat() if fixture.match_date else None,
                         "home_team_id": fixture.home_team_id, "away_team_id": fixture.away_team_id,
                         "home_goals": result.home_goals, "away_goals": result.away_goals}
                        for fixture, result in rows]}

class ToolRegistry:
    def __init__(self):
        self._tools = {
            "search_fixtures": ToolSpec("search_fixtures", "Search real fixtures already stored in MATCH X. Returns no invented data.",
                                        SearchFixturesArgs, _search_fixtures),
            "resolve_team": ToolSpec("resolve_team", "Resolve a team name using stored teams and explicit aliases. Report ambiguity instead of guessing.",
                                     ResolveTeamArgs, _resolve_team),
            "get_fixture_analysis": ToolSpec("get_fixture_analysis", "Retrieve one stored fixture, its saved prediction and available result. No prediction is generated by this tool.",
                                             FixtureAnalysisArgs, _fixture_analysis),
            "get_team_form": ToolSpec("get_team_form", "Return recent stored completed results and a transparent W/D/L/goals summary for a team ID.",
                                      TeamFormArgs, _team_form),
            "get_head_to_head": ToolSpec("get_head_to_head", "Return recent stored completed meetings for two resolved team IDs.",
                                         HeadToHeadArgs, _head_to_head),
        }

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.model_schema() for tool in self._tools.values()]

    async def dispatch(self, name: str, raw_arguments: str, db: AsyncSession) -> dict[str, Any]:
        spec = self._tools.get(name)
        if spec is None:
            return {"status": "unsupported_tool", "message": "This tool is not allowlisted."}
        try:
            args = spec.arguments.model_validate_json(raw_arguments)
        except ValueError:
            return {"status": "invalid_arguments", "message": "Tool arguments failed schema validation."}
        try:
            result = await asyncio.wait_for(spec.handler(args, db), timeout=6.0)
            return result
        except TimeoutError:
            return {"status": "tool_timeout", "message": "The data query timed out."}
        except Exception as exc:
            # Do not pass exception messages, SQL, or internal details back to the model.
            return {"status": "tool_error", "error_type": type(exc).__name__,
                    "message": "The data query failed. Do not infer missing facts."}
