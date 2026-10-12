"""Dixon-Coles football score model with weighted likelihood and identifiable strengths."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import exp
from typing import Sequence

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

from app.prediction.poisson import ScorelineGrid, build_scoreline_grid

class ModelFitError(ValueError):
    """Training data or numerical optimization was not adequate for a model fit."""

@dataclass(frozen=True)
class MatchObservation:
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    played_at: datetime
    closing_odds: tuple[float, float, float] | None = None

@dataclass(frozen=True)
class DixonColesModel:
    team_names: tuple[str, ...]
    attack_strength: dict[str, float]
    defence_vulnerability: dict[str, float]
    league_home_goals: float
    league_away_goals: float
    home_advantage: float
    rho: float
    time_decay_days: float
    data_cutoff: datetime
    training_matches: int
    weighted_log_likelihood: float
    optimizer_message: str

    def expected_goals(self, home_team: str, away_team: str) -> tuple[float, float]:
        if home_team not in self.attack_strength or away_team not in self.attack_strength:
            raise ModelFitError("Insufficient data: team is absent from the fitted model.")
        home_rate = self.league_home_goals * self.attack_strength[home_team] \
                    * self.defence_vulnerability[away_team] * self.home_advantage
        away_rate = self.league_away_goals * self.attack_strength[away_team] \
                    * self.defence_vulnerability[home_team]
        if not (0 < home_rate <= 8 and 0 < away_rate <= 8):
            raise ModelFitError("Unsupported expected-goal rate above 8.0 for the configured score grid.")
        return home_rate, away_rate

    def scoreline_grid(self, home_team: str, away_team: str, cap: int = 20) -> ScorelineGrid:
        home_rate, away_rate = self.expected_goals(home_team, away_team)
        grid = build_scoreline_grid(home_rate, away_rate, cap)
        corrected: dict[tuple[int, int], float] = {}
        for (home_goals, away_goals), probability in grid.probabilities.items():
            correction = _tau(home_goals, away_goals, home_rate, away_rate, self.rho)
            if correction <= 0:
                raise ModelFitError("Dixon-Coles low-score correction is non-positive for this fixture.")
            corrected[(home_goals, away_goals)] = probability * correction
        mass = sum(corrected.values())
        if mass <= 0 or not np.isfinite(mass):
            raise ModelFitError("Dixon-Coles correction produced invalid scoreline mass.")
        retained_mass = mass * grid.retained_mass
        if retained_mass < 0.9999:
            raise ModelFitError(f"Dixon-Coles grid retained only {retained_mass:.8f} probability mass.")
        normalised = {score: probability / mass for score, probability in corrected.items()}
        return ScorelineGrid(normalised, retained_mass)

def _tau(home_goals: int, away_goals: int, home_rate: float, away_rate: float, rho: float) -> float:
    if home_goals == 0 and away_goals == 0:
        return 1.0 - home_rate * away_rate * rho
    if home_goals == 0 and away_goals == 1:
        return 1.0 + home_rate * rho
    if home_goals == 1 and away_goals == 0:
        return 1.0 + away_rate * rho
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0

def _log_poisson(goals: np.ndarray, rate: np.ndarray) -> np.ndarray:
    return goals * np.log(rate) - rate - gammaln(goals + 1)

def fit_dixon_coles(
    observations: Sequence[MatchObservation],
    *,
    data_cutoff: datetime,
    time_decay_days: float = 365.0,
    min_matches: int = 50,
    min_team_matches: int = 3,
    l2_penalty: float = 0.01,
) -> DixonColesModel:
    """Fit only matches strictly before data_cutoff; decay older matches exponentially.

    Select time_decay_days on a separate chronological validation window. This function
    deliberately does not tune on the same data it reports as training likelihood.
    """
    if data_cutoff.tzinfo is None:
        raise ModelFitError("data_cutoff must be timezone-aware.")
    if time_decay_days <= 0 or min_matches < 1 or min_team_matches < 1 or l2_penalty < 0:
        raise ValueError("Invalid model fitting configuration.")
    cutoff = data_cutoff.astimezone(timezone.utc)
    matches: list[MatchObservation] = []
    for match in observations:
        if match.played_at.tzinfo is None:
            raise ModelFitError("Every training timestamp must be timezone-aware.")
        if match.played_at.astimezone(timezone.utc) < cutoff:
            if (not match.home_team or not match.away_team or match.home_team == match.away_team
                or isinstance(match.home_goals, bool) or isinstance(match.away_goals, bool)
                or match.home_goals < 0 or match.away_goals < 0):
                raise ModelFitError("Invalid match observation.")
            matches.append(match)
    if len(matches) < min_matches:
        raise ModelFitError(f"Insufficient data: need {min_matches} pre-cutoff matches; found {len(matches)}.")
    teams = tuple(sorted({m.home_team for m in matches} | {m.away_team for m in matches}))
    if len(teams) < 4:
        raise ModelFitError("Insufficient data: at least four distinct teams are required.")
    team_index = {team: index for index, team in enumerate(teams)}
    appearances = {team: 0 for team in teams}
    for match in matches:
        appearances[match.home_team] += 1
        appearances[match.away_team] += 1
    sparse = [team for team, count in appearances.items() if count < min_team_matches]
    if sparse:
        raise ModelFitError(f"Insufficient recent matches for {len(sparse)} teams.")

    home_idx = np.asarray([team_index[m.home_team] for m in matches], dtype=int)
    away_idx = np.asarray([team_index[m.away_team] for m in matches], dtype=int)
    home_goals = np.asarray([m.home_goals for m in matches], dtype=float)
    away_goals = np.asarray([m.away_goals for m in matches], dtype=float)
    ages = np.asarray([(cutoff - m.played_at.astimezone(timezone.utc)).total_seconds() / 86400
                       for m in matches], dtype=float)
    weights = np.exp(-np.maximum(ages, 0) / time_decay_days)
    home_baseline = float(np.average(home_goals, weights=weights))
    away_baseline = float(np.average(away_goals, weights=weights))
    if home_baseline <= 0 or away_baseline <= 0:
        raise ModelFitError("Insufficient scoring variation for positive league goal-rate priors.")
    n_teams = len(teams)
    parameter_count = 2 * (n_teams - 1) + 2

    def unpack(parameters: np.ndarray):
        attacks = np.concatenate((parameters[:n_teams - 1], [-np.sum(parameters[:n_teams - 1])]))
        defence_start = n_teams - 1
        defence_partial = parameters[defence_start:defence_start + n_teams - 1]
        defences = np.concatenate((defence_partial, [-np.sum(defence_partial)]))
        log_home_advantage = float(parameters[-2])
        rho = float(parameters[-1])
        return attacks, defences, log_home_advantage, rho

    def objective(parameters: np.ndarray) -> float:
        attacks, defences, log_home_advantage, rho = unpack(parameters)
        home_rates = home_baseline * np.exp(attacks[home_idx] + defences[away_idx] + log_home_advantage)
        away_rates = away_baseline * np.exp(attacks[away_idx] + defences[home_idx])
        tau = np.ones(len(matches), dtype=float)
        zero_zero = (home_goals == 0) & (away_goals == 0)
        zero_one = (home_goals == 0) & (away_goals == 1)
        one_zero = (home_goals == 1) & (away_goals == 0)
        one_one = (home_goals == 1) & (away_goals == 1)
        tau[zero_zero] = 1 - home_rates[zero_zero] * away_rates[zero_zero] * rho
        tau[zero_one] = 1 + home_rates[zero_one] * rho
        tau[one_zero] = 1 + away_rates[one_zero] * rho
        tau[one_one] = 1 - rho
        if np.any(tau <= 0) or not np.all(np.isfinite(tau)):
            return 1e100
        log_likelihood = np.log(tau) + _log_poisson(home_goals, home_rates) + _log_poisson(away_goals, away_rates)
        penalty = l2_penalty * (float(np.sum(attacks ** 2)) + float(np.sum(defences ** 2)))
        return -float(np.sum(weights * log_likelihood)) + penalty

    initial = np.zeros(parameter_count, dtype=float)
    bounds = [(-2.5, 2.5)] * (2 * (n_teams - 1)) + [(-1.0, 1.0), (-0.2, 0.2)]
    fitted = minimize(objective, initial, method="L-BFGS-B", bounds=bounds,
                      options={"maxiter": 2500, "ftol": 1e-10})
    if not fitted.success or not np.all(np.isfinite(fitted.x)):
        raise ModelFitError(f"Dixon-Coles optimizer failed: {fitted.message}")
    attacks, defences, log_home_advantage, rho = unpack(fitted.x)
    return DixonColesModel(
        team_names=teams,
        attack_strength={team: exp(float(attacks[i])) for i, team in enumerate(teams)},
        defence_vulnerability={team: exp(float(defences[i])) for i, team in enumerate(teams)},
        league_home_goals=home_baseline,
        league_away_goals=away_baseline,
        home_advantage=exp(log_home_advantage),
        rho=rho,
        time_decay_days=time_decay_days,
        data_cutoff=cutoff,
        training_matches=len(matches),
        weighted_log_likelihood=-float(fitted.fun) + l2_penalty * (float(np.sum(attacks ** 2)) + float(np.sum(defences ** 2))),
        optimizer_message=str(fitted.message),
    )


@dataclass(frozen=True)
class TimeDecaySelection:
    best_days: float
    mean_log_loss_by_days: dict[float, float]
    folds_used: int

def select_time_decay(
    observations: Sequence[MatchObservation],
    *,
    data_cutoff: datetime,
    candidates: Sequence[float] = (90.0, 180.0, 365.0, 730.0),
    folds: int = 3,
    min_training_matches: int = 50,
) -> TimeDecaySelection:
    """Choose exponential decay by expanding-window, chronological validation only."""
    if data_cutoff.tzinfo is None:
        raise ModelFitError("data_cutoff must be timezone-aware.")
    if folds < 1 or min_training_matches < 1:
        raise ValueError("folds and min_training_matches must be positive.")
    candidate_days = tuple(sorted({float(days) for days in candidates}))
    if not candidate_days or any(days <= 0 or not np.isfinite(days) for days in candidate_days):
        raise ValueError("Every time-decay candidate must be finite and positive.")
    cutoff = data_cutoff.astimezone(timezone.utc)
    eligible = []
    for match in observations:
        if match.played_at.tzinfo is None:
            raise ModelFitError("Every training timestamp must be timezone-aware.")
        if match.played_at.astimezone(timezone.utc) < cutoff:
            eligible.append(match)
    eligible.sort(key=lambda match: match.played_at.astimezone(timezone.utc))
    if len(eligible) < min_training_matches + folds * 5:
        raise ModelFitError("Insufficient data for expanding-window time-decay validation.")
    fold_size = min(max(5, len(eligible) // 10),
                    max(1, (len(eligible) - min_training_matches) // folds))
    starts = [len(eligible) - folds * fold_size + index * fold_size for index in range(folds)]
    scores: dict[float, list[float]] = {days: [] for days in candidate_days}
    for start in starts:
        validation = eligible[start:start + fold_size]
        if not validation:
            continue
        fold_cutoff = min(match.played_at.astimezone(timezone.utc) for match in validation)
        for days in candidate_days:
            try:
                model = fit_dixon_coles(
                    eligible, data_cutoff=fold_cutoff, time_decay_days=days,
                    min_matches=min_training_matches, min_team_matches=1,
                )
            except ModelFitError:
                continue
            losses: list[float] = []
            for match in validation:
                if match.home_team not in model.attack_strength or match.away_team not in model.attack_strength:
                    continue
                home_rate, away_rate = model.expected_goals(match.home_team, match.away_team)
                correction = _tau(match.home_goals, match.away_goals, home_rate, away_rate, model.rho)
                if correction <= 0:
                    losses.append(1e6)
                    continue
                log_probability = (
                    np.log(correction)
                    + match.home_goals * np.log(home_rate) - home_rate - gammaln(match.home_goals + 1)
                    + match.away_goals * np.log(away_rate) - away_rate - gammaln(match.away_goals + 1)
                )
                losses.append(float(-log_probability))
            if losses:
                scores[days].append(float(np.mean(losses)))
    means = {days: float(np.mean(values)) for days, values in scores.items() if values}
    if not means:
        raise ModelFitError("No valid chronological validation fold could be fitted.")
    best = min(means, key=means.get)
    return TimeDecaySelection(best_days=best, mean_log_loss_by_days=means, folds_used=min(len(v) for v in scores.values() if v))
