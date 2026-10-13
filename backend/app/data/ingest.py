from dataclasses import dataclass, field
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..config import KNOWN_LEAGUES
from ..db import utcnow
from ..models import Competition, Fixture, MatchResult, Team
from .provider import NormMatch

@dataclass
class IngestReport:
    fixtures_new: int = 0
    fixtures_updated: int = 0
    results_recorded: int = 0
    skipped_invalid: int = 0
    notes: list = field(default_factory=list)


def get_or_create_competition(s: Session, code: str) -> Competition:
    c = s.scalar(select(Competition).where(Competition.code == code))
    if not c:
        c = Competition(code=code, name=KNOWN_LEAGUES.get(code, code), enabled=True)
        s.add(c); s.flush()
    return c


def _team(s: Session, provider: str, pid: int, name: str, short: str | None, tla: str | None) -> Team:
    t = s.scalar(select(Team).where(Team.provider == provider, Team.provider_id == pid))
    if not t:
        t = Team(provider=provider, provider_id=pid, name=name, short_name=short, tla=tla)
        s.add(t); s.flush()
    return t


def ingest_matches(s: Session, provider: str, matches: list[NormMatch]) -> IngestReport:
    rep = IngestReport()
    now = utcnow()
    for m in matches:
        if m.home_id == m.away_id:
            rep.skipped_invalid += 1; continue
        finished = m.status == "FINISHED"
        if finished and (m.home_goals is None or m.away_goals is None or m.home_goals < 0 or m.away_goals < 0):
            rep.skipped_invalid += 1; continue   # final status but no usable score: never guess
        comp = get_or_create_competition(s, m.competition_code)
        home = _team(s, provider, m.home_id, m.home_name, m.home_short, m.home_tla)
        away = _team(s, provider, m.away_id, m.away_name, m.away_short, m.away_tla)
        fx = s.scalar(select(Fixture).where(Fixture.provider == provider,
                                            Fixture.provider_fixture_id == m.provider_fixture_id))
        if fx is None:
            fx = Fixture(provider=provider, provider_fixture_id=m.provider_fixture_id, competition_id=comp.id,
                         season=m.season, matchday=m.matchday, utc_kickoff=m.utc_kickoff, status=m.status,
                         home_team_id=home.id, away_team_id=away.id, fetched_at=now)
            s.add(fx); s.flush(); rep.fixtures_new += 1
        else:
            fx.utc_kickoff, fx.status, fx.matchday, fx.fetched_at = m.utc_kickoff, m.status, m.matchday, now
            rep.fixtures_updated += 1
        if finished and s.scalar(select(MatchResult).where(MatchResult.fixture_id == fx.id)) is None:
            s.add(MatchResult(fixture_id=fx.id, home_goals=m.home_goals, away_goals=m.away_goals))
            rep.results_recorded += 1
    s.commit()
    return rep
