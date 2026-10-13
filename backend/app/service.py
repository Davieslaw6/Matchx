"""Training (separate operation) and prediction orchestration."""
from __future__ import annotations
import math
import pandas as pd
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import Settings
from .db import utcnow
from .engine.dixon_coles import FitConfig, fit, model_from_dict, model_to_dict
from .engine.errors import InsufficientDataError
from .engine.validation import validate_prediction
from .models import AppSetting, Competition, Fixture, MatchResult, ModelRegistry, Prediction, PredictionEvaluation


def _history(s: Session, comp: Competition, provider: str) -> pd.DataFrame:
    rows = s.execute(select(Fixture.utc_kickoff, Fixture.home_team_id, Fixture.away_team_id,
                            MatchResult.home_goals, MatchResult.away_goals)
                     .join(MatchResult, MatchResult.fixture_id == Fixture.id)
                     .where(Fixture.competition_id == comp.id, Fixture.provider == provider)).all()
    return pd.DataFrame([dict(date=r[0], home=str(r[1]), away=str(r[2]), home_goals=r[3], away_goals=r[4])
                         for r in rows], columns=["date", "home", "away", "home_goals", "away_goals"])


def train_competition(s: Session, cfg: Settings, code: str, provider: str, as_of: datetime | None = None) -> ModelRegistry:
    comp = s.scalar(select(Competition).where(Competition.code == code))
    if not comp:
        raise InsufficientDataError(f"Unknown competition {code}")
    as_of = as_of or utcnow()
    model = fit(_history(s, comp, provider), as_of, FitConfig(half_life_days=cfg.half_life_days))
    version = f"{provider}-{code}-{model.version}"
    for old in s.scalars(select(ModelRegistry).where(ModelRegistry.competition_id == comp.id,
                                                      ModelRegistry.provider == provider, ModelRegistry.is_active == True)):  # noqa: E712
        old.is_active = False
    reg = ModelRegistry(competition_id=comp.id, provider=provider, version=version, as_of=as_of, n_matches=model.n_matches,
                        params=model_to_dict(model), metrics=None, is_active=True)
    s.add(reg); s.commit()
    return reg


class NoModelError(Exception):
    pass


def predict_fixture(s: Session, cfg: Settings, fixture_id: int, provider: str, store: bool = True) -> dict:
    fx = s.get(Fixture, fixture_id)
    if fx is None:
        raise InsufficientDataError("Unknown fixture")
    if fx.provider != provider:
        raise InsufficientDataError(f"Fixture belongs to provider '{fx.provider}', but '{provider}' is selected")
    if fx.competition.code not in cfg.leagues:
        raise InsufficientDataError(f"{fx.competition.code} is not an enabled competition")
    if fx.status not in ("SCHEDULED", "TIMED"):
        raise InsufficientDataError(f"Fixture status is {fx.status}; only upcoming fixtures can be predicted")
    reg = s.scalar(select(ModelRegistry).where(ModelRegistry.competition_id == fx.competition_id,
                                               ModelRegistry.provider == provider, ModelRegistry.is_active == True))  # noqa: E712
    if reg is None:
        raise NoModelError("No trained model for this competition. Run sync, then training.")
    model = model_from_dict(reg.params)
    pred = model.predict(str(fx.home_team_id), str(fx.away_team_id))
    validate_prediction(pred)
    warnings = list(pred["warnings"])
    now = utcnow()
    if (now - reg.trained_at).total_seconds() > cfg.stale_after_hours * 3600:
        warnings.append(f"Model was trained {int((now - reg.trained_at).total_seconds() // 3600)}h ago; may be stale.")
    last_sync = s.get(AppSetting, f"last_sync:{provider}:{fx.competition.code}")
    if last_sync is None:
        warnings.append("No recorded data sync for this competition.")
    elif (now - last_sync.updated_at).total_seconds() > cfg.stale_after_hours * 3600:
        warnings.append("Fixture/result data has not been refreshed recently.")
    warnings.append("No xG, injury or lineup data is used; goals-only model.")
    out = {
        "fixture_id": fx.id, "provider": provider, "home_team": fx.home_team.name, "away_team": fx.away_team.name,
        "competition": fx.competition.name, "kickoff_utc": fx.utc_kickoff.isoformat(),
        "model_version": reg.version,
        **{k: pred[k] for k in ("data_cutoff", "expected_home_goals", "expected_away_goals",
                                "result", "double_chance", "over", "under", "btts", "top_scorelines", "coverage")},
        "warnings": warnings,
        "data_timestamps": {"model_trained_at": reg.trained_at.isoformat(),
                            "fixture_fetched_at": fx.fetched_at.isoformat(),
                            "last_sync": last_sync.updated_at.isoformat() if last_sync else None},
    }
    if not store:
        return out
    row = Prediction(fixture_id=fx.id, model_version=reg.version,
                     data_cutoff=pd.Timestamp(pred["data_cutoff"]).to_pydatetime(),
                     home_win=pred["result"]["home"], draw=pred["result"]["draw"], away_win=pred["result"]["away"],
                     payload=out)
    s.add(row); s.commit()
    out["prediction_id"] = row.id
    return out


def evaluate_predictions(s: Session) -> int:
    """Score stored predictions whose fixtures now have results (log loss + Brier on 1X2)."""
    n = 0
    rows = s.execute(select(Prediction, MatchResult).join(MatchResult, MatchResult.fixture_id == Prediction.fixture_id)
                     .outerjoin(PredictionEvaluation, PredictionEvaluation.prediction_id == Prediction.id)
                     .where(PredictionEvaluation.id.is_(None))).all()
    for p, r in rows:
        probs = [p.home_win, p.draw, p.away_win]
        actual = 0 if r.home_goals > r.away_goals else 1 if r.home_goals == r.away_goals else 2
        y = [1.0 if i == actual else 0.0 for i in range(3)]
        s.add(PredictionEvaluation(prediction_id=p.id, home_goals=r.home_goals, away_goals=r.away_goals,
                                   log_loss=-math.log(max(probs[actual], 1e-12)),
                                   brier=sum((a - b) ** 2 for a, b in zip(probs, y))))
        n += 1
    s.commit()
    return n


def backtest_competition(s: Session, cfg: Settings, code: str, provider: str) -> dict:
    from .engine.backtest import backtest
    comp = s.scalar(select(Competition).where(Competition.code == code))
    if not comp:
        raise InsufficientDataError(f"Unknown competition {code}")
    res = backtest(_history(s, comp, provider), FitConfig(half_life_days=cfg.half_life_days))
    reg = s.scalar(select(ModelRegistry).where(ModelRegistry.competition_id == comp.id, ModelRegistry.provider == provider,
                                               ModelRegistry.is_active == True))  # noqa: E712
    if reg is not None:
        reg.metrics = {"backtest": res, "run_at": utcnow().isoformat()}
        s.commit()
    return res
