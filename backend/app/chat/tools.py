"""Narrow, read-only tools the LLM may call. All numbers come from the DB or the prediction engine."""
from __future__ import annotations
from datetime import date, timedelta
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from ..config import Settings
from ..db import utcnow
from ..engine.errors import InsufficientDataError
from ..fixtures import match_teams, resolve_fixture
from ..models import Competition, Fixture, MatchResult, ModelRegistry, Prediction, PredictionEvaluation
from ..service import NoModelError, evaluate_predictions, predict_fixture

MARKETS = {  # market key -> path into prediction payload
    "home_win": ("result", "home"), "draw": ("result", "draw"), "away_win": ("result", "away"),
    "1X": ("double_chance", "1X"), "X2": ("double_chance", "X2"), "12": ("double_chance", "12"),
    "over_0.5": ("over", "0.5"), "over_1.5": ("over", "1.5"), "over_2.5": ("over", "2.5"), "over_3.5": ("over", "3.5"),
    "under_0.5": ("under", "0.5"), "under_1.5": ("under", "1.5"), "under_2.5": ("under", "2.5"), "under_3.5": ("under", "3.5"),
    "btts_yes": ("btts", "yes"), "btts_no": ("btts", "no"),
}


def _obj(**p):
    return {"type": "object", "properties": p, "additionalProperties": False}


S, I, N = {"type": "string"}, {"type": "integer"}, {"type": "number"}
TOOL_SPECS = [
    {"name": "search_fixtures", "description": "Find verified upcoming fixtures. Give home and away team (home first), or only a competition code (PL, PD, SA, BL1, FL1) to list the next fixtures. Optional date YYYY-MM-DD.",
     "parameters": _obj(home=S, away=S, competition=S, date=S)},
    {"name": "get_fixture_details", "description": "Details of one fixture by fixture_id.", "parameters": {**_obj(fixture_id=I), "required": ["fixture_id"]}},
    {"name": "get_team_form", "description": "Most recent finished matches for a team (n between 3 and 20) with W/D/L and goals.", "parameters": {**_obj(team=S, n=I), "required": ["team"]}},
    {"name": "get_head_to_head", "description": "Stored head-to-head finished matches between two teams.", "parameters": {**_obj(team_a=S, team_b=S), "required": ["team_a", "team_b"]}},
    {"name": "get_team_statistics", "description": "Home and away goals scored/conceded averages for a team from stored results.", "parameters": {**_obj(team=S), "required": ["team"]}},
    {"name": "calculate_match_prediction", "description": "Run the statistical prediction engine for an upcoming fixture_id. The ONLY source of probabilities.", "parameters": {**_obj(fixture_id=I), "required": ["fixture_id"]}},
    {"name": "search_upcoming_predictions", "description": "Scan upcoming fixtures of a competition for a market with probability >= min_probability. Markets: " + ", ".join(MARKETS),
     "parameters": {**_obj(competition=S, market=S, min_probability=N, days_ahead=I, limit=I), "required": ["competition", "market"]}},
    {"name": "get_model_evaluation", "description": "Historical performance (log loss, Brier) of stored predictions vs a uniform baseline, plus model versions.", "parameters": _obj()},
]


def _one_team(s, name, provider):
    ts = match_teams(s, name, provider)
    if not ts:
        return None, {"error": f"No team matching '{name}' in the selected data provider's stored data."}
    if len(ts) > 1:
        return None, {"error": f"'{name}' is ambiguous", "candidates": [t.name for t in ts[:5]]}
    return ts[0], None


def _fx(f: Fixture) -> dict:
    return {"fixture_id": f.id, "home": f.home_team.name, "away": f.away_team.name, "competition": f.competition.name,
            "competition_code": f.competition.code, "kickoff_utc": f.utc_kickoff.isoformat(), "status": f.status}


def _finished(s, provider, team_ids, limit=None, both=False):
    q = (select(Fixture, MatchResult).join(MatchResult, MatchResult.fixture_id == Fixture.id)
         .where(Fixture.provider == provider))
    if both:
        a, b = team_ids
        q = q.where(or_((Fixture.home_team_id == a) & (Fixture.away_team_id == b), (Fixture.home_team_id == b) & (Fixture.away_team_id == a)))
    else:
        q = q.where(or_(Fixture.home_team_id == team_ids, Fixture.away_team_id == team_ids))
    q = q.order_by(Fixture.utc_kickoff.desc())
    return s.execute(q.limit(limit) if limit else q).all()


def search_fixtures(s, cfg, provider, home=None, away=None, competition=None, date=None):
    d = date and __import__("datetime").date.fromisoformat(date)
    if home and away:
        r = resolve_fixture(s, provider, home, away, competition, d)
        return {"status": r.status, "message": r.message, "fixtures": [_fx(f) for f in r.fixtures]}
    if competition:
        q = (select(Fixture).join(Competition).where(Competition.code == competition.upper(), Fixture.provider == provider,
                                                     Fixture.status.in_(["TIMED", "SCHEDULED"]), Fixture.utc_kickoff >= utcnow())
             .order_by(Fixture.utc_kickoff).limit(10))
        return {"status": "found", "fixtures": [_fx(f) for f in s.scalars(q)]}
    return {"status": "need_more_info", "message": "Provide both teams, or a competition code."}


def get_fixture_details(s, cfg, provider, fixture_id):
    f = s.get(Fixture, fixture_id)
    return _fx(f) if f else {"error": "Unknown fixture_id"}


def get_team_form(s, cfg, provider, team, n=10):
    t, err = _one_team(s, team, provider)
    if err: return err
    n = max(3, min(int(n), 20))
    rows = _finished(s, provider, t.id, n)
    if not rows:
        return {"team": t.name, "error": "No stored finished matches (data unavailable, not zero)."}
    ms = []
    w = d = l = gf = ga = 0
    for f, r in rows:
        home = f.home_team_id == t.id
        for_, ag = (r.home_goals, r.away_goals) if home else (r.away_goals, r.home_goals)
        res = "W" if for_ > ag else "D" if for_ == ag else "L"
        w += res == "W"; d += res == "D"; l += res == "L"; gf += for_; ga += ag
        ms.append({"date": f.utc_kickoff.date().isoformat(), "venue": "H" if home else "A",
                   "opponent": (f.away_team if home else f.home_team).name, "score": f"{for_}-{ag}", "result": res})
    k = len(rows)
    out = {"team": t.name, "matches_used": k, "wins": w, "draws": d, "losses": l, "goals_for": gf, "goals_against": ga,
           "win_pct": round(100 * w / k, 1), "matches": ms}
    if k < n:
        out["note"] = f"Only {k} matches stored (requested {n})."
    return out


def get_head_to_head(s, cfg, provider, team_a, team_b):
    a, e1 = _one_team(s, team_a, provider)
    if e1: return e1
    b, e2 = _one_team(s, team_b, provider)
    if e2: return e2
    rows = _finished(s, provider, (a.id, b.id), both=True)
    if not rows:
        return {"matches_used": 0, "note": "No head-to-head stored in the available history (limited by data plan)."}
    return {"matches_used": len(rows), "note": "Only stored history is covered.",
            "matches": [{"date": f.utc_kickoff.date().isoformat(), "home": f.home_team.name, "away": f.away_team.name,
                         "score": f"{r.home_goals}-{r.away_goals}"} for f, r in rows]}


def get_team_statistics(s, cfg, provider, team):
    t, err = _one_team(s, team, provider)
    if err: return err
    rows = _finished(s, provider, t.id)
    if not rows:
        return {"team": t.name, "error": "No stored finished matches (data unavailable, not zero)."}
    agg = {"home": [0, 0, 0], "away": [0, 0, 0]}
    for f, r in rows:
        k = "home" if f.home_team_id == t.id else "away"
        gf, ga = (r.home_goals, r.away_goals) if k == "home" else (r.away_goals, r.home_goals)
        agg[k][0] += 1; agg[k][1] += gf; agg[k][2] += ga
    out = {"team": t.name, "matches_used": len(rows)}
    for k, (n, gf, ga) in agg.items():
        out[k] = {"played": n, "goals_for_avg": round(gf / n, 2) if n else None, "goals_against_avg": round(ga / n, 2) if n else None}
    return out


def calculate_match_prediction(s, cfg, provider, fixture_id):
    try:
        return predict_fixture(s, cfg, int(fixture_id), provider)
    except (InsufficientDataError, NoModelError) as e:
        return {"declined": True, "reason": str(e)}


def search_upcoming_predictions(s, cfg, provider, competition, market, min_probability=0.0, days_ahead=14, limit=10):
    if market not in MARKETS:
        return {"error": f"Unknown market. Use one of: {', '.join(MARKETS)}"}
    a, b = MARKETS[market]
    q = (select(Fixture).join(Competition).where(Competition.code == competition.upper(), Fixture.provider == provider,
                                                 Fixture.status.in_(["TIMED", "SCHEDULED"]), Fixture.utc_kickoff >= utcnow(),
                                                 Fixture.utc_kickoff <= utcnow() + timedelta(days=max(1, min(int(days_ahead), 60))))
         .order_by(Fixture.utc_kickoff))
    hits, skipped = [], 0
    for f in s.scalars(q):
        try:
            p = predict_fixture(s, cfg, f.id, provider, store=False)
        except (InsufficientDataError, NoModelError):
            skipped += 1; continue
        pr = p[a][b]
        if pr >= float(min_probability):
            hits.append({**_fx(f), "market": market, "probability": pr, "expected_home_goals": p["expected_home_goals"],
                         "expected_away_goals": p["expected_away_goals"]})
    hits.sort(key=lambda x: -x["probability"])
    return {"matches": hits[: max(1, min(int(limit), 20))], "fixtures_skipped_no_prediction": skipped,
            "note": "Probability is not value or confidence; no odds are used."}


def get_model_evaluation(s, cfg, provider):
    evaluate_predictions(s)
    n, ll, br = s.execute(select(func.count(PredictionEvaluation.id), func.avg(PredictionEvaluation.log_loss),
                                 func.avg(PredictionEvaluation.brier))).one()
    models = s.scalars(select(ModelRegistry).where(ModelRegistry.provider == provider)
                       .order_by(ModelRegistry.trained_at.desc()).limit(5)).all()
    out = {"evaluated_predictions": n, "uniform_baseline": {"log_loss": 1.0986, "brier": 0.6667},
           "models": [{"version": m.version, "trained_at": m.trained_at.isoformat(), "n_matches": m.n_matches, "active": m.is_active} for m in models]}
    active = next((m for m in models if m.is_active and m.metrics and m.metrics.get("backtest")), None)
    if active:
        b = active.metrics["backtest"]
        out["backtest"] = {"n_predictions": b["n_predictions"], "model": b["model"], "baseline_outcome_frequencies": b["baseline_outcome_frequencies"],
                           "verdict": b["verdict"], "period": f"{b['first_prediction']} to {b['last_match']}", "version": active.version}
    if n:
        out["mean_log_loss"], out["mean_brier"] = round(ll, 4), round(br, 4)
    if n < 30:
        out["warning"] = f"Only {n} evaluated live predictions: too few to claim accuracy." + ("" if active else " No backtest has been run yet.")
    return out


REGISTRY = {f.__name__: f for f in (search_fixtures, get_fixture_details, get_team_form, get_head_to_head, get_team_statistics,
                                    calculate_match_prediction, search_upcoming_predictions, get_model_evaluation)}
