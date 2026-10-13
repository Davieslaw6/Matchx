import numpy as np, pandas as pd, pytest
from scipy.stats import poisson
from app.engine.markets import score_matrix, derive_markets, tau
from app.engine.dixon_coles import fit
from app.engine.errors import InsufficientDataError


def test_poisson_formula_matches_independent_model():
    m, _ = score_matrix(1.4, 1.1, rho=0.0, max_goals=15)
    assert m[2, 1] == pytest.approx(poisson.pmf(2, 1.4) * poisson.pmf(1, 1.1), rel=1e-6)


def test_matrix_sums_to_one_and_truncation_small():
    m, lost = score_matrix(2.2, 1.6, rho=-0.08)
    assert m.sum() == pytest.approx(1.0)
    assert lost < 1e-3


def test_dixon_coles_correction_values():
    assert tau(0, 0, 1.2, 1.0, -0.1) == pytest.approx(1 + 0.12)
    assert tau(0, 1, 1.2, 1.0, -0.1) == pytest.approx(1 - 0.12)
    assert tau(1, 0, 1.2, 1.0, -0.1) == pytest.approx(1 - 0.1)
    assert tau(1, 1, 1.2, 1.0, -0.1) == pytest.approx(1.1)
    assert tau(2, 2, 1.2, 1.0, -0.1) == 1.0


def test_negative_rho_raises_nil_nil_vs_independent():
    ind, _ = score_matrix(1.3, 1.1, 0.0)
    dc, _ = score_matrix(1.3, 1.1, -0.1)
    assert dc[0, 0] > ind[0, 0] * 0.99  # correction applied (pre-normalisation inflates 0-0)
    assert dc[1, 1] > ind[1, 1] * 0.99


def test_invalid_lambda_rejected():
    with pytest.raises(ValueError):
        score_matrix(0.0, 1.0)


@pytest.mark.parametrize("lh,la,rho", [(1.5, 1.2, -0.05), (0.6, 2.4, 0.0), (3.0, 0.5, -0.1)])
def test_market_consistency(lh, la, rho):
    m, _ = score_matrix(lh, la, rho)
    k = derive_markets(m)
    r = k["result"]
    assert sum(r.values()) == pytest.approx(1.0)
    dc = k["double_chance"]
    assert dc["1X"] == pytest.approx(r["home"] + r["draw"])
    assert dc["X2"] == pytest.approx(r["draw"] + r["away"])
    assert dc["12"] == pytest.approx(r["home"] + r["away"])
    for line in k["over"]:
        assert k["over"][line] + k["under"][line] == pytest.approx(1.0)
    assert k["over"]["0.5"] >= k["over"]["1.5"] >= k["over"]["2.5"] >= k["over"]["3.5"]
    assert k["btts"]["yes"] + k["btts"]["no"] == pytest.approx(1.0)


def test_btts_independent_closed_form():
    lh, la = 1.3, 0.9
    m, _ = score_matrix(lh, la, 0.0, max_goals=20)
    expected = (1 - np.exp(-lh)) * (1 - np.exp(-la))
    assert derive_markets(m)["btts"]["yes"] == pytest.approx(expected, abs=1e-6)


def test_correct_score_ranking_sorted_and_matches_matrix():
    m, _ = score_matrix(1.8, 1.0, -0.05)
    top = derive_markets(m, top_n=5)["top_scorelines"]
    probs = [t["probability"] for t in top]
    assert probs == sorted(probs, reverse=True)
    i, j = map(int, top[0]["score"].split("-"))
    assert m[i, j] == pytest.approx(m.max())


def test_fit_recovers_ordering(model):
    s_h, s_a = model.expected_goals("Strong", "Weak")
    w_h, w_a = model.expected_goals("Weak", "Strong")
    assert s_h > s_a and w_h < w_a
    assert model.home_adv > 0
    p = model.predict("Strong", "Weak")
    assert p["result"]["home"] > p["result"]["away"]
    assert -0.2 <= model.rho <= 0.2


def test_prediction_structure(model):
    p = model.predict("Mid1", "Mid2")
    for key in ["expected_home_goals", "expected_away_goals", "model_version", "data_cutoff", "coverage", "warnings"]:
        assert key in p
    assert sum(p["result"].values()) == pytest.approx(1.0)


def test_no_future_leakage(data):
    cutoff = data["date"].iloc[len(data) // 2]
    base = fit(data, cutoff)
    future = data[data["date"] >= cutoff].copy()
    future["home_goals"] += 9  # absurd future results must not matter
    tampered = pd.concat([data[data["date"] < cutoff], future])
    other = fit(tampered, cutoff)
    assert np.allclose(base.att, other.att) and base.home_adv == pytest.approx(other.home_adv)
    assert base.n_matches == (data["date"] < cutoff).sum()


def test_missing_goals_are_dropped_not_zeroed(data):
    d = data.copy().astype({"home_goals": float})
    d.loc[d.index[:10], "home_goals"] = np.nan
    m = fit(d, d["date"].max() + pd.Timedelta(days=1))
    assert m.n_matches == len(data) - 10


def test_duplicates_removed(data):
    d = pd.concat([data, data.iloc[:20]])
    m = fit(d, d["date"].max() + pd.Timedelta(days=1))
    assert m.n_matches == len(data)


def test_insufficient_data_declines(data):
    with pytest.raises(InsufficientDataError):
        fit(data.iloc[:20], data["date"].max() + pd.Timedelta(days=1))


def test_unknown_team_declines(model):
    with pytest.raises(InsufficientDataError):
        model.predict("Atlantis FC", "Strong")


def test_missing_columns_declines(data):
    with pytest.raises(InsufficientDataError):
        fit(data.drop(columns=["home_goals"]), "2030-01-01")
