from datetime import datetime, timedelta, timezone

import pytest

from app.prediction.backtest import walk_forward_backtest
from app.prediction.dixon_coles import MatchObservation, ModelFitError, fit_dixon_coles, select_time_decay
from app.prediction.poisson import derive_markets

def sample_matches():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    teams = [f"Team {i}" for i in range(6)]
    matches = []
    for index in range(160):
        home = teams[index % len(teams)]
        away = teams[(index * 5 + 1) % len(teams)]
        matches.append(MatchObservation(
            home_team=home,
            away_team=away,
            home_goals=(index * 7) % 4,
            away_goals=(index * 5 + 1) % 3,
            played_at=start + timedelta(days=index * 5),
        ))
    return matches

def test_fit_dixon_coles_produces_normalized_markets():
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    model = fit_dixon_coles(sample_matches(), data_cutoff=cutoff, min_matches=50)
    grid = model.scoreline_grid("Team 0", "Team 1")
    assert grid.retained_mass >= 0.9999
    assert abs(sum(grid.probabilities.values()) - 1.0) < 1e-9
    markets = derive_markets(grid)
    assert abs(markets.home_win + markets.draw + markets.away_win - 1.0) < 1e-9
    assert all(probability >= 0 for probability in grid.probabilities.values())

def test_post_cutoff_matches_cannot_change_fit():
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    historical = sample_matches()
    first = fit_dixon_coles(historical, data_cutoff=cutoff, min_matches=50)
    leaked = historical + [MatchObservation("Team 0", "Team 1", 10, 0, cutoff + timedelta(days=1))]
    second = fit_dixon_coles(leaked, data_cutoff=cutoff, min_matches=50)
    assert first.attack_strength == second.attack_strength
    assert first.defence_vulnerability == second.defence_vulnerability
    assert first.rho == second.rho
    assert first.weighted_log_likelihood == second.weighted_log_likelihood

def test_insufficient_pre_cutoff_data_returns_reason():
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ModelFitError, match="Insufficient data"):
        fit_dixon_coles(sample_matches()[:10], data_cutoff=cutoff, min_matches=50)

def test_naive_cutoff_is_rejected():
    with pytest.raises(ModelFitError, match="timezone-aware"):
        fit_dixon_coles(sample_matches(), data_cutoff=datetime(2026, 1, 1), min_matches=50)

def test_time_decay_is_selected_with_expanding_chronological_folds():
    selection = select_time_decay(
        sample_matches(),
        data_cutoff=datetime(2026, 1, 1, tzinfo=timezone.utc),
        candidates=(180, 365),
        folds=2,
        min_training_matches=50,
    )
    assert selection.best_days in (180.0, 365.0)
    assert selection.folds_used >= 1
    assert set(selection.mean_log_loss_by_days) <= {180.0, 365.0}

def test_walk_forward_backtest_reports_baselines_and_uncertainty():
    report = walk_forward_backtest(
        sample_matches(),
        data_cutoff=datetime(2026, 1, 1, tzinfo=timezone.utc),
        initial_train_matches=100,
        test_window_matches=20,
        tune_time_decay=False,
        bootstrap_replicates=50,
    )
    assert report["status"] == "completed"
    assert report["metrics"]["m1_dixon_coles"]["sample_size"] > 0
    assert report["metrics"]["m0_poisson"]["sample_size"] == report["metrics"]["m1_dixon_coles"]["sample_size"]
    assert "m1_minus_m0_poisson_log_loss" in report["comparisons"]
    assert len(report["metrics"]["m1_dixon_coles"]["log_loss_ci95"]) == 2
