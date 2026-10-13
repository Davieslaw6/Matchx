import numpy as np, pandas as pd, pytest

TEAMS = ["Strong", "Mid1", "Mid2", "Mid3", "Mid4", "Weak"]
ATT = {"Strong": 0.4, "Mid1": 0.1, "Mid2": 0.0, "Mid3": -0.05, "Mid4": -0.1, "Weak": -0.35}
DFN = {"Strong": -0.3, "Mid1": -0.05, "Mid2": 0.0, "Mid3": 0.05, "Mid4": 0.1, "Weak": 0.3}


def synth(seed=7, rounds=8, start="2023-08-01"):
    """Deterministic synthetic league (clearly synthetic: used for tests only)."""
    rng = np.random.default_rng(seed)
    rows, d = [], pd.Timestamp(start, tz="UTC")
    for _ in range(rounds):
        for h in TEAMS:
            for a in TEAMS:
                if h == a:
                    continue
                lh = np.exp(0.2 + 0.25 + ATT[h] + DFN[a]); la = np.exp(0.2 + ATT[a] + DFN[h])
                rows.append(dict(date=d, home=h, away=a, home_goals=rng.poisson(lh), away_goals=rng.poisson(la)))
                d += pd.Timedelta(days=1)
    return pd.DataFrame(rows)


@pytest.fixture(scope="session")
def data():
    return synth()


@pytest.fixture(scope="session")
def model(data):
    from app.engine.dixon_coles import fit
    return fit(data, data["date"].max() + pd.Timedelta(days=1))
