import pytest
from app.prediction.poisson import build_scoreline_grid, derive_markets

def test_scoreline_grid_retains_mass_and_is_nonnegative():
    grid = build_scoreline_grid(1.45, 1.1)
    assert grid.retained_mass > 0.9999
    assert all(p >= 0 for p in grid.probabilities.values())
    assert sum(grid.probabilities.values()) == pytest.approx(1.0)

def test_derived_market_invariants():
    markets = derive_markets(build_scoreline_grid(1.6, 0.9))
    assert markets.home_win + markets.draw + markets.away_win == pytest.approx(1.0)
    assert markets.btts_yes + markets.btts_no == pytest.approx(1.0)
    assert all(0 <= p <= 1 for p in markets.over.values())
    assert list(markets.over.values()) == sorted(markets.over.values(), reverse=True)

def test_invalid_expected_goals_rejected():
    with pytest.raises(ValueError):
        build_scoreline_grid(0, 1.1)
