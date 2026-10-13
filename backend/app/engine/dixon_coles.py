"""Time-decayed, ridge-regularised Dixon-Coles model fitted with SciPy.

log lam_home = home_adv + att[home] + dfn[away]
log lam_away =            att[away] + dfn[home]      (dfn higher = leakier defence)
Only matches strictly before `as_of` are used (no future-data leakage).
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from .errors import InsufficientDataError
from .markets import derive_markets, score_matrix

REQUIRED = ["date", "home", "away", "home_goals", "away_goals"]


@dataclass
class FitConfig:
    half_life_days: float = 365.0   # weight halves every year
    ridge: float = 0.5              # shrinks small-sample teams to average
    min_team_matches: int = 8
    min_total_matches: int = 60
    rho_bound: float = 0.2


@dataclass
class DixonColesModel:
    teams: list
    att: np.ndarray
    dfn: np.ndarray
    home_adv: float
    mu: float
    rho: float
    as_of: pd.Timestamp
    n_matches: int
    match_counts: dict
    version: str
    min_team_matches: int = 8

    def expected_goals(self, home: str, away: str) -> tuple[float, float]:
        for t in (home, away):
            if t not in self.match_counts:
                raise InsufficientDataError(f"No history for team '{t}'")
            if self.match_counts[t] < self.min_team_matches:
                raise InsufficientDataError(f"Only {self.match_counts[t]} matches for '{t}'; need {self.min_team_matches}")
        i, j = self.teams.index(home), self.teams.index(away)
        lh = np.exp(self.mu + self.home_adv + self.att[i] + self.dfn[j])
        la = np.exp(self.mu + self.att[j] + self.dfn[i])
        return float(lh), float(la)

    def predict(self, home: str, away: str, top_n: int = 5) -> dict:
        lh, la = self.expected_goals(home, away)
        m, lost = score_matrix(lh, la, self.rho)
        out = derive_markets(m, top_n)
        out.update(expected_home_goals=lh, expected_away_goals=la,
                   truncated_probability_mass=lost, model_version=self.version,
                   data_cutoff=self.as_of.isoformat(),
                   coverage={"home_matches": self.match_counts[home],
                             "away_matches": self.match_counts[away],
                             "total_matches": self.n_matches})
        warnings = []
        for t in (home, away):
            if self.match_counts[t] < 20:
                warnings.append(f"Limited history for {t} ({self.match_counts[t]} matches): estimates are shrunk toward average.")
        out["warnings"] = warnings
        return out


def _prepare(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise InsufficientDataError(f"Missing columns: {missing}")
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], utc=True)
    d = d.dropna(subset=REQUIRED)  # unavailable != zero: rows with missing goals are dropped, never filled
    d = d[d["date"] < as_of]
    d = d.drop_duplicates(subset=["date", "home", "away"])
    if ((d["home_goals"] < 0) | (d["away_goals"] < 0)).any():
        raise InsufficientDataError("Negative goals in data")
    return d.sort_values("date").reset_index(drop=True)


def fit(df: pd.DataFrame, as_of, cfg: FitConfig | None = None) -> DixonColesModel:
    cfg = cfg or FitConfig()
    as_of = pd.Timestamp(as_of)
    as_of = as_of.tz_localize("UTC") if as_of.tzinfo is None else as_of.tz_convert("UTC")
    d = _prepare(df, as_of)
    if len(d) < cfg.min_total_matches:
        raise InsufficientDataError(f"Only {len(d)} matches before {as_of.date()}; need {cfg.min_total_matches}")
    teams = sorted(set(d["home"]) | set(d["away"]))
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    hi = d["home"].map(idx).to_numpy()
    ai = d["away"].map(idx).to_numpy()
    x = d["home_goals"].to_numpy(int)
    y = d["away_goals"].to_numpy(int)
    age = (as_of - d["date"]).dt.total_seconds().to_numpy() / 86400.0
    w = 0.5 ** (age / cfg.half_life_days)
    counts = {t: int(((d["home"] == t) | (d["away"] == t)).sum()) for t in teams}
    mu0 = float(np.log(max((x.sum() + y.sum()) / (2 * len(d)), 1e-3)))

    def unpack(p):
        return p[:n], p[n:2 * n], p[2 * n], p[2 * n + 1]

    def nll(p):
        att, dfn, ha, rho = unpack(p)
        lh = np.exp(mu0 + ha + att[hi] + dfn[ai])
        la = np.exp(mu0 + att[ai] + dfn[hi])
        t = np.ones_like(lh)
        m00, m01, m10, m11 = (x == 0) & (y == 0), (x == 0) & (y == 1), (x == 1) & (y == 0), (x == 1) & (y == 1)
        t[m00] = 1 - lh[m00] * la[m00] * rho
        t[m01] = 1 + lh[m01] * rho
        t[m10] = 1 + la[m10] * rho
        t[m11] = 1 - rho
        if (t <= 0).any():
            return 1e12
        ll = np.log(t) + x * np.log(lh) - lh + y * np.log(la) - la  # constant factorials dropped
        pen = cfg.ridge * (np.sum(att ** 2) + np.sum(dfn ** 2)) + 10.0 * (att.sum() ** 2 + dfn.sum() ** 2)
        return -(w * ll).sum() + pen

    p0 = np.zeros(2 * n + 2)
    p0[2 * n] = 0.25
    bounds = [(None, None)] * (2 * n) + [(None, None), (-cfg.rho_bound, cfg.rho_bound)]
    res = minimize(nll, p0, method="L-BFGS-B", bounds=bounds)
    if not res.success and not np.isfinite(res.fun):
        raise InsufficientDataError("Model fit failed to converge")
    att, dfn, ha, rho = unpack(res.x)
    return DixonColesModel(teams, att - att.mean(), dfn - dfn.mean(), float(ha), mu0, float(rho),
                           as_of, len(d), counts, f"dc-v1-hl{int(cfg.half_life_days)}-{as_of.date()}", cfg.min_team_matches)


def model_to_dict(m: DixonColesModel) -> dict:
    return {"teams": m.teams, "att": m.att.tolist(), "dfn": m.dfn.tolist(), "home_adv": m.home_adv,
            "mu": m.mu, "rho": m.rho, "as_of": m.as_of.isoformat(), "n_matches": m.n_matches,
            "match_counts": m.match_counts, "version": m.version, "min_team_matches": m.min_team_matches}


def model_from_dict(d: dict) -> DixonColesModel:
    return DixonColesModel(d["teams"], np.array(d["att"]), np.array(d["dfn"]), d["home_adv"], d["mu"], d["rho"],
                           pd.Timestamp(d["as_of"]), d["n_matches"], d["match_counts"], d["version"],
                           d.get("min_team_matches", 8))
