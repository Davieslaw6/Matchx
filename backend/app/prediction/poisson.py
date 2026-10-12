"""Deterministic independent-Poisson baseline and derived football markets."""
from __future__ import annotations
from dataclasses import dataclass
from math import exp, factorial
from typing import Mapping

@dataclass(frozen=True)
class ScorelineGrid:
    probabilities: Mapping[tuple[int, int], float]
    retained_mass: float

@dataclass(frozen=True)
class MarketProbabilities:
    home_win: float
    draw: float
    away_win: float
    over: Mapping[float, float]
    btts_yes: float
    btts_no: float
    correct_scores: tuple[tuple[int, int, float], ...]

def _poisson_pmf(rate: float, goals: int) -> float:
    if rate <= 0 or goals < 0:
        raise ValueError("rate must be positive and goals must be non-negative")
    return exp(-rate) * rate**goals / factorial(goals)

def build_scoreline_grid(home_xg: float, away_xg: float, cap: int = 10) -> ScorelineGrid:
    """Build a truncated independent Poisson grid; reject invalid or insufficient mass."""
    if not (0 < home_xg <= 12 and 0 < away_xg <= 12):
        raise ValueError("expected goals must be in (0, 12]")
    if not 5 <= cap <= 20:
        raise ValueError("cap must be between 5 and 20")
    grid = {(h, a): _poisson_pmf(home_xg, h) * _poisson_pmf(away_xg, a)
            for h in range(cap + 1) for a in range(cap + 1)}
    mass = sum(grid.values())
    if mass < 0.9999:
        raise ValueError(f"scoreline cap retained only {mass:.8f} probability mass")
    normalised = {score: probability / mass for score, probability in grid.items()}
    return ScorelineGrid(normalised, mass)

def derive_markets(grid: ScorelineGrid, top_n: int = 5) -> MarketProbabilities:
    if top_n < 1:
        raise ValueError("top_n must be positive")
    p_home = sum(p for (h, a), p in grid.probabilities.items() if h > a)
    p_draw = sum(p for (h, a), p in grid.probabilities.items() if h == a)
    p_away = sum(p for (h, a), p in grid.probabilities.items() if h < a)
    over = {line: sum(p for (h, a), p in grid.probabilities.items() if h + a > line)
            for line in (0.5, 1.5, 2.5, 3.5, 4.5)}
    yes = sum(p for (h, a), p in grid.probabilities.items() if h > 0 and a > 0)
    scores = sorted(((h, a, p) for (h, a), p in grid.probabilities.items()),
                    key=lambda item: (-item[2], item[0], item[1]))[:top_n]
    return MarketProbabilities(p_home, p_draw, p_away, over, yes, 1.0 - yes, tuple(scores))

def expected_goals(home_attack: float, away_defence: float, away_attack: float,
                   home_defence: float, league_home_goals: float, league_away_goals: float,
                   home_advantage: float = 1.08) -> tuple[float, float]:
    """Combine positive attack/defence multipliers with league goal rates."""
    values = (home_attack, away_defence, away_attack, home_defence,
              league_home_goals, league_away_goals, home_advantage)
    if any(value <= 0 for value in values):
        raise ValueError("strength multipliers and league rates must be positive")
    return (league_home_goals * home_attack * away_defence * home_advantage,
            league_away_goals * away_attack * home_defence / home_advantage)
