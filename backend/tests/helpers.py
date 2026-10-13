"""Deterministic, clearly synthetic provider payloads in football-data.org v4 shape (TEST DATA ONLY)."""
import numpy as np
from datetime import datetime, timedelta, timezone

NAMES = ["Manchester City FC", "Arsenal FC", "Chelsea FC", "Everton FC", "Fulham FC", "Burnley FC"]
ATT = [0.4, 0.15, 0.05, -0.05, -0.1, -0.35]
DFN = [-0.3, -0.1, 0.0, 0.05, 0.1, 0.3]


def raw_match(mid, kick, h, a, status, hg=None, ag=None, season_start="2026-08-01", code="PL"):
    return {"id": mid, "utcDate": kick.strftime("%Y-%m-%dT%H:%M:%SZ"), "status": status, "matchday": 1,
            "season": {"startDate": season_start},
            "homeTeam": {"id": 100 + h, "name": NAMES[h], "shortName": NAMES[h].replace(" FC", ""), "tla": NAMES[h][:3].upper()},
            "awayTeam": {"id": 100 + a, "name": NAMES[a], "shortName": NAMES[a].replace(" FC", ""), "tla": NAMES[a][:3].upper()},
            "score": {"fullTime": {"home": hg, "away": ag}}}


def league_payload(rounds=3, seed=3, future=((0, 5), (5, 0))):
    rng = np.random.default_rng(seed)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    n_games = rounds * 30
    day = now - timedelta(days=n_games + 2)
    out, mid = [], 1
    for r in range(rounds):
        season_start = f"{2026 - rounds + r}-08-01"   # one round-robin per season (real-league uniqueness)
        for h in range(6):
            for a in range(6):
                if h == a: continue
                lh = np.exp(0.2 + 0.25 + ATT[h] + DFN[a]); la = np.exp(0.2 + ATT[a] + DFN[h])
                out.append(raw_match(mid, day, h, a, "FINISHED", int(rng.poisson(lh)), int(rng.poisson(la)), season_start=season_start))
                mid += 1; day += timedelta(days=1)
    for i, (h, a) in enumerate(future):
        out.append(raw_match(10_000 + i, now + timedelta(days=3 + i), h, a, "TIMED"))
    return {"matches": out}


def af_payload(fd_payload):
    """Re-shape the synthetic league into API-Football v3 form with different ids/names (TEST DATA ONLY)."""
    out = []
    short = {"FINISHED": "FT", "TIMED": "NS"}
    for r in fd_payload["matches"]:
        fin = r["status"] == "FINISHED"
        ft = r["score"]["fullTime"]
        out.append({"fixture": {"id": r["id"] + 50_000, "date": r["utcDate"].replace("Z", "+00:00"), "status": {"short": short[r["status"]]}},
                    "league": {"id": 39, "season": int(r["season"]["startDate"][:4]), "round": f"Regular Season - {r['matchday']}"},
                    "teams": {"home": {"id": r["homeTeam"]["id"] + 7000, "name": r["homeTeam"]["name"]},
                              "away": {"id": r["awayTeam"]["id"] + 7000, "name": r["awayTeam"]["name"]}},
                    "goals": {"home": ft["home"] if fin else None, "away": ft["away"] if fin else None},
                    "score": {"fulltime": {"home": ft["home"] if fin else None, "away": ft["away"] if fin else None}}})
    return {"errors": [], "results": len(out), "response": out}
