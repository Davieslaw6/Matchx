"""Walk-forward (chronological) backtest: every block is predicted by a model fitted ONLY on earlier matches."""
from __future__ import annotations
import math
import numpy as np
import pandas as pd
from .dixon_coles import FitConfig, fit
from .errors import InsufficientDataError

BINS = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0001]


def _outcome(hg, ag) -> int:
    return 0 if hg > ag else 1 if hg == ag else 2


def backtest(df: pd.DataFrame, cfg: FitConfig | None = None, min_train: int = 120, block_days: int = 14) -> dict:
    cfg = cfg or FitConfig()
    d = df.dropna(subset=["date", "home", "away", "home_goals", "away_goals"]).copy()
    d["date"] = pd.to_datetime(d["date"], utc=True)
    d = d.drop_duplicates(subset=["date", "home", "away"]).sort_values("date").reset_index(drop=True)
    if len(d) <= min_train + 10:
        raise InsufficientDataError(f"Need more than {min_train + 10} matches to backtest; have {len(d)}")
    start = d["date"].iloc[min_train]
    end = d["date"].iloc[-1]
    probs, actual, base_probs = [], [], []
    t = start
    while t <= end:
        block = d[(d["date"] >= t) & (d["date"] < t + pd.Timedelta(days=block_days))]
        train = d[d["date"] < t]
        if len(block):
            try:
                model = fit(train, t, cfg)
                freq = np.bincount([_outcome(h, a) for h, a in zip(train["home_goals"], train["away_goals"])], minlength=3) + 1.0
                freq = freq / freq.sum()
                for _, m in block.iterrows():
                    try:
                        p = model.predict(m["home"], m["away"])["result"]
                    except InsufficientDataError:
                        continue    # unseen / thin team: skipped, never imputed
                    probs.append([p["home"], p["draw"], p["away"]])
                    base_probs.append(freq.tolist())
                    actual.append(_outcome(m["home_goals"], m["away_goals"]))
            except InsufficientDataError:
                pass
        t += pd.Timedelta(days=block_days)
    if not actual:
        raise InsufficientDataError("Backtest produced no predictions")
    P, B, A = np.array(probs), np.array(base_probs), np.array(actual)
    Y = np.eye(3)[A]

    def ll(Q): return float(-np.mean(np.log(np.clip(Q[np.arange(len(A)), A], 1e-12, 1))))
    def br(Q): return float(np.mean(np.sum((Q - Y) ** 2, axis=1)))

    flat_p, flat_y = P.ravel(), Y.ravel()
    cal = []
    for lo, hi in zip(BINS[:-1], BINS[1:]):
        mask = (flat_p >= lo) & (flat_p < hi)
        if mask.sum():
            cal.append({"bin": f"{lo:.1f}-{min(hi, 1.0):.1f}", "n": int(mask.sum()),
                        "mean_predicted": float(flat_p[mask].mean()), "observed_freq": float(flat_y[mask].mean())})
    return {"n_predictions": len(A), "blocks_days": block_days, "min_train": min_train,
            "first_prediction": str(start.date()), "last_match": str(end.date()),
            "model": {"log_loss": ll(P), "brier": br(P)},
            "baseline_outcome_frequencies": {"log_loss": ll(B), "brier": br(B)},
            "baseline_uniform": {"log_loss": math.log(3), "brier": 2 / 3},
            "calibration": cal,
            "verdict": "better than frequency baseline" if ll(P) < ll(B) else "NOT better than frequency baseline"}
