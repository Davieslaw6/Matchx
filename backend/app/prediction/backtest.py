"""Chronological walk-forward evaluation for football 1X2 forecasts."""
from __future__ import annotations

from datetime import datetime, timezone
from math import log
from typing import Any, Sequence

import numpy as np

from app.prediction.dixon_coles import (
    MatchObservation,
    ModelFitError,
    fit_dixon_coles,
    select_time_decay,
)
from app.prediction.poisson import build_scoreline_grid, derive_markets

OUTCOMES = ("home", "draw", "away")

def _actual_index(match: MatchObservation) -> int:
    return 0 if match.home_goals > match.away_goals else 2 if match.home_goals < match.away_goals else 1

def _valid_market_probabilities(odds: tuple[float, float, float] | None) -> tuple[float, float, float] | None:
    if odds is None or len(odds) != 3 or any(not np.isfinite(value) or value <= 1 for value in odds):
        return None
    implied = np.asarray([1.0 / value for value in odds], dtype=float)
    total = float(implied.sum())
    if total <= 0:
        return None
    probabilities = implied / total
    return tuple(float(value) for value in probabilities)

def _metrics(probabilities: Sequence[tuple[float, float, float]], actual: Sequence[int],
             *, bins: int = 10, bootstrap_replicates: int = 1000, seed: int = 42) -> dict[str, Any]:
    if not probabilities:
        return {"sample_size": 0, "log_loss": None, "brier": None, "rps": None,
                "ece": None, "sharpness": None, "log_loss_ci95": None}
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(actual, dtype=int)
    p = np.clip(p, 1e-12, 1.0)
    p = p / p.sum(axis=1, keepdims=True)
    one_hot = np.eye(3)[y]
    losses = -np.log(p[np.arange(len(y)), y])
    brier = np.sum((p - one_hot) ** 2, axis=1)
    cumulative_p = np.cumsum(p, axis=1)[:, :2]
    cumulative_y = np.cumsum(one_hot, axis=1)[:, :2]
    rps = np.mean((cumulative_p - cumulative_y) ** 2, axis=1)
    confidence = np.max(p, axis=1)
    correct = (np.argmax(p, axis=1) == y).astype(float)
    ece = 0.0
    bin_edges = np.linspace(0.0, 1.0, bins + 1)
    calibration = []
    for index in range(bins):
        selected = (confidence >= bin_edges[index]) & (
            confidence <= bin_edges[index + 1] if index == bins - 1 else confidence < bin_edges[index + 1]
        )
        count = int(np.sum(selected))
        if count:
            accuracy = float(np.mean(correct[selected]))
            mean_confidence = float(np.mean(confidence[selected]))
            ece += count / len(y) * abs(accuracy - mean_confidence)
            calibration.append({"lower": float(bin_edges[index]), "upper": float(bin_edges[index + 1]),
                                "count": count, "accuracy": accuracy, "confidence": mean_confidence})
    rng = np.random.default_rng(seed)
    if bootstrap_replicates > 0 and len(losses) > 1:
        samples = rng.integers(0, len(losses), size=(bootstrap_replicates, len(losses)))
        boot_means = np.mean(losses[samples], axis=1)
        ci = [float(np.quantile(boot_means, 0.025)), float(np.quantile(boot_means, 0.975))]
    else:
        ci = [float(np.mean(losses)), float(np.mean(losses))]
    return {
        "sample_size": int(len(y)),
        "log_loss": float(np.mean(losses)),
        "log_loss_ci95": ci,
        "brier": float(np.mean(brier)),
        "rps": float(np.mean(rps)),
        "ece": float(ece),
        "sharpness": float(np.mean(confidence)),
        "calibration": calibration,
    }

def walk_forward_backtest(
    observations: Sequence[MatchObservation],
    *,
    data_cutoff: datetime,
    initial_train_matches: int = 100,
    test_window_matches: int = 20,
    time_decay_candidates: Sequence[float] = (90.0, 180.0, 365.0, 730.0),
    tune_time_decay: bool = True,
    bootstrap_replicates: int = 1000,
    seed: int = 42,
) -> dict[str, Any]:
    """Run expanding-window forecasts; every forecast uses only earlier observations."""
    if data_cutoff.tzinfo is None:
        raise ModelFitError("data_cutoff must be timezone-aware.")
    if initial_train_matches < 50 or test_window_matches < 1:
        raise ValueError("initial_train_matches must be >= 50 and test_window_matches must be positive.")
    cutoff = data_cutoff.astimezone(timezone.utc)
    ordered = []
    for match in observations:
        if match.played_at.tzinfo is None:
            raise ModelFitError("Every match timestamp must be timezone-aware.")
        if match.played_at.astimezone(timezone.utc) < cutoff:
            ordered.append(match)
    ordered.sort(key=lambda match: match.played_at.astimezone(timezone.utc))
    if len(ordered) <= initial_train_matches:
        raise ModelFitError("Insufficient data for a walk-forward test window.")

    forecasts: dict[str, list[tuple[float, float, float]]] = {
        "uniform": [], "league_base_rate": [], "m0_poisson": [], "m1_dixon_coles": [], "closing_market": [],
    }
    actual: dict[str, list[int]] = {name: [] for name in forecasts}
    fold_reports: list[dict[str, Any]] = []
    skipped: dict[str, int] = {"unseen_team": 0, "model_fit": 0, "invalid_grid": 0}
    cursor = initial_train_matches
    fold_index = 0
    while cursor < len(ordered):
        training = ordered[:cursor]
        test = ordered[cursor:cursor + test_window_matches]
        fold_cutoff = min(match.played_at.astimezone(timezone.utc) for match in test)
        try:
            if tune_time_decay:
                selection = select_time_decay(
                    training, data_cutoff=fold_cutoff, candidates=time_decay_candidates,
                    folds=2, min_training_matches=50,
                )
                decay_days = selection.best_days
                decay_scores = selection.mean_log_loss_by_days
            else:
                decay_days = 365.0
                decay_scores = {}
            model = fit_dixon_coles(training, data_cutoff=fold_cutoff,
                                    time_decay_days=decay_days, min_matches=50)
        except ModelFitError as exc:
            fold_reports.append({"fold": fold_index, "status": "skipped", "reason": str(exc),
                                 "training_matches": len(training), "test_matches": len(test)})
            cursor += test_window_matches
            fold_index += 1
            continue

        home_base = float(np.mean([m.home_goals for m in training]))
        away_base = float(np.mean([m.away_goals for m in training]))
        outcome_counts = np.ones(3, dtype=float)
        for match in training:
            outcome_counts[_actual_index(match)] += 1
        base_rate = outcome_counts / outcome_counts.sum()
        fold_scored = 0
        for match in test:
            outcome = _actual_index(match)
            uniform = (1 / 3, 1 / 3, 1 / 3)
            base_prob = tuple(float(value) for value in base_rate)
            forecasts["uniform"].append(uniform)
            actual["uniform"].append(outcome)
            forecasts["league_base_rate"].append(base_prob)
            actual["league_base_rate"].append(outcome)
            market = _valid_market_probabilities(match.closing_odds)
            if market is not None:
                forecasts["closing_market"].append(market)
                actual["closing_market"].append(outcome)
            try:
                m0_grid = build_scoreline_grid(home_base, away_base)
                m0 = derive_markets(m0_grid)
                m0_prob = (m0.home_win, m0.draw, m0.away_win)
                forecasts["m0_poisson"].append(m0_prob)
                actual["m0_poisson"].append(outcome)
            except ValueError:
                skipped["invalid_grid"] += 1
            try:
                m1_grid = model.scoreline_grid(match.home_team, match.away_team)
                m1 = derive_markets(m1_grid)
                forecasts["m1_dixon_coles"].append((m1.home_win, m1.draw, m1.away_win))
                actual["m1_dixon_coles"].append(outcome)
                fold_scored += 1
            except ModelFitError:
                skipped["unseen_team"] += 1
            except ValueError:
                skipped["invalid_grid"] += 1
        fold_reports.append({
            "fold": fold_index, "status": "evaluated", "cutoff": fold_cutoff.isoformat(),
            "training_matches": len(training), "test_matches": len(test),
            "m1_predictions": fold_scored, "selected_time_decay_days": decay_days,
            "time_decay_validation_log_loss": decay_scores,
        })
        cursor += test_window_matches
        fold_index += 1

    metrics = {
        name: _metrics(values, actual[name], bootstrap_replicates=bootstrap_replicates,
                       seed=seed + index)
        for index, (name, values) in enumerate(forecasts.items())
    }
    comparisons = {}
    for baseline in ("m0_poisson", "uniform", "league_base_rate"):
        common = min(len(actual["m1_dixon_coles"]), len(actual[baseline]))
        if common:
            # Forecast lists are produced in the same chronological order for shared models.
            m1_losses = [-log(max(forecasts["m1_dixon_coles"][i][actual["m1_dixon_coles"][i]], 1e-12))
                         for i in range(common)]
            baseline_losses = [-log(max(forecasts[baseline][i][actual[baseline][i]], 1e-12))
                               for i in range(common)]
            differences = np.asarray(m1_losses) - np.asarray(baseline_losses)
            rng = np.random.default_rng(seed + 100 + len(comparisons))
            if len(differences) > 1 and bootstrap_replicates:
                draws = rng.integers(0, len(differences), size=(bootstrap_replicates, len(differences)))
                boot = np.mean(differences[draws], axis=1)
                ci = [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))]
            else:
                ci = [float(np.mean(differences)), float(np.mean(differences))]
            comparisons[f"m1_minus_{baseline}_log_loss"] = {
                "sample_size": common, "mean_difference": float(np.mean(differences)),
                "bootstrap_ci95": ci,
                "interpretation": "negative favours M1; positive favours the baseline",
            }
    return {
        "status": "completed" if metrics["m1_dixon_coles"]["sample_size"] else "insufficient_data",
        "data_cutoff": cutoff.isoformat(),
        "eligible_matches": len(ordered),
        "folds": fold_reports,
        "metrics": metrics,
        "comparisons": comparisons,
        "skipped": skipped,
        "seed": seed,
        "bootstrap_replicates": bootstrap_replicates,
        "market_baseline_status": "evaluated" if metrics["closing_market"]["sample_size"] else "unavailable_no_valid_closing_odds",
    }
