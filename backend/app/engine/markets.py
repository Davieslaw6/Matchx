"""Scoreline matrix and every market derived from that single matrix."""
from __future__ import annotations
import numpy as np
from scipy.stats import poisson

MAX_GOALS = 10


def tau(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    """Dixon-Coles low-score dependence correction."""
    if x == 0 and y == 0:
        return 1.0 - lam * mu * rho
    if x == 0 and y == 1:
        return 1.0 + lam * rho
    if x == 1 and y == 0:
        return 1.0 + mu * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def score_matrix(lam_home: float, lam_away: float, rho: float = 0.0,
                 max_goals: int = MAX_GOALS) -> tuple[np.ndarray, float]:
    """Return (matrix[h, a], truncated_mass_lost). Matrix is renormalised to sum to 1.

    rho=0 gives the independent-Poisson model (documented assumption).
    """
    if lam_home <= 0 or lam_away <= 0:
        raise ValueError("expected goals must be positive")
    k = np.arange(max_goals + 1)
    m = np.outer(poisson.pmf(k, lam_home), poisson.pmf(k, lam_away))
    for x in (0, 1):
        for y in (0, 1):
            t = tau(x, y, lam_home, lam_away, rho)
            if t <= 0:
                raise ValueError("rho/lambda combination yields non-positive probability")
            m[x, y] *= t
    total = m.sum()
    return m / total, float(max(0.0, 1.0 - total))


def derive_markets(m: np.ndarray, top_n: int = 5) -> dict:
    h, a = np.indices(m.shape)
    home, draw, away = m[h > a].sum(), m[h == a].sum(), m[h < a].sum()
    tot = h + a
    over = {f"{line}": float(m[tot > line].sum()) for line in (0.5, 1.5, 2.5, 3.5)}
    under = {k: 1.0 - v for k, v in over.items()}
    btts_yes = float(m[(h > 0) & (a > 0)].sum())
    order = np.dstack(np.unravel_index(np.argsort(-m, axis=None), m.shape))[0][:top_n]
    return {
        "result": {"home": float(home), "draw": float(draw), "away": float(away)},
        "double_chance": {"1X": float(home + draw), "X2": float(draw + away), "12": float(home + away)},
        "over": over,
        "under": under,
        "btts": {"yes": btts_yes, "no": 1.0 - btts_yes},
        "top_scorelines": [{"score": f"{int(i)}-{int(j)}", "probability": float(m[i, j])} for i, j in order],
    }
