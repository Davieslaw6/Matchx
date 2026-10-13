"""Resolve a user's team names to a verified upcoming fixture."""
from __future__ import annotations
import difflib, re, unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import utcnow
from .models import Competition, Fixture, Team

ALIASES = {
    "man city": "manchester city", "man utd": "manchester united", "man united": "manchester united",
    "spurs": "tottenham hotspur", "tottenham": "tottenham hotspur", "wolves": "wolverhampton wanderers",
    "newcastle": "newcastle united", "brighton": "brighton hove albion", "west ham": "west ham united",
    "inter": "internazionale milano", "inter milan": "internazionale milano", "psg": "paris saint germain",
    "atletico": "atletico madrid", "barca": "barcelona", "real": "real madrid", "bayern": "bayern munchen",
    "dortmund": "borussia dortmund", "leverkusen": "bayer leverkusen", "gladbach": "borussia monchengladbach",
}
NOISE = {"fc", "afc", "cf", "ac", "as", "ssc", "us", "rc", "sc", "fk", "club", "de", "calcio"}


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = " ".join(w for w in s.split() if w not in NOISE)
    return ALIASES.get(s, s)


def match_teams(s: Session, query: str, provider: str) -> list[Team]:
    q = norm(query)
    teams = s.scalars(select(Team).where(Team.provider == provider)).all()
    exact = [t for t in teams if q in {norm(t.name), norm(t.short_name or ""), (t.tla or "").lower()}]
    if exact:
        return exact
    sub = [t for t in teams if q and (q in norm(t.name) or norm(t.name) in q)]
    if sub:
        return sub
    scored = [(difflib.SequenceMatcher(None, q, norm(t.name)).ratio(), t) for t in teams]
    return [t for r, t in sorted(scored, key=lambda x: -x[0]) if r >= 0.8][:3]


@dataclass
class Resolution:
    status: str                      # found | ambiguous | not_found
    fixtures: list = field(default_factory=list)
    message: str = ""


def resolve_fixture(s: Session, provider: str, home_q: str, away_q: str, competition: str | None = None,
                    on_date: date | None = None) -> Resolution:
    ht, at = match_teams(s, home_q, provider), match_teams(s, away_q, provider)
    if not ht or not at:
        missing = home_q if not ht else away_q
        return Resolution("not_found", message=f"I couldn't find a team matching '{missing}' in the enabled leagues. "
                                               "Please give the full team name or the competition.")
    q = select(Fixture).where(Fixture.home_team_id.in_([t.id for t in ht]),
                              Fixture.away_team_id.in_([t.id for t in at]),
                              Fixture.provider == provider,
                              Fixture.status.in_(["SCHEDULED", "TIMED", "POSTPONED"]),
                              Fixture.utc_kickoff >= utcnow() - timedelta(hours=3)).order_by(Fixture.utc_kickoff)
    if competition:
        q = q.join(Competition).where(Competition.code == competition.upper())
    fx = list(s.scalars(q))
    if on_date:
        fx = [f for f in fx if f.utc_kickoff.date() == on_date]
    if not fx:
        return Resolution("not_found", message="No upcoming fixture found for that home/away pairing. "
                                               "Check team order (home team first), the date, or the competition.")
    if len(fx) > 1:
        return Resolution("ambiguous", fx, "Multiple upcoming fixtures match; please specify the date or competition.")
    return Resolution("found", fx)
