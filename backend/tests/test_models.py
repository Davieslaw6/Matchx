from app.models import Base

def test_required_persistence_tables_exist():
    required = {
        "app_settings", "conversations", "messages", "teams", "competitions",
        "fixtures", "match_results", "team_statistics", "market_odds", "predictions",
        "prediction_evaluations", "tickets", "ticket_selections", "uploaded_files",
        "booking_code_jobs", "data_sync_runs", "model_registry", "sessions",
        "team_aliases", "idempotency_keys", "provider_raw_payloads", "api_quota_usage",
        "ticket_revisions", "owner_accounts", "login_attempts", "booking_code_selections",
    }
    assert required <= set(Base.metadata.tables)

def test_fixture_provider_identity_is_unique():
    constraints = Base.metadata.tables["fixtures"].constraints
    assert any(
        getattr(constraint, "name", None) == "uq_fixture_provider_id"
        for constraint in constraints
    )

def test_odds_are_observations_with_decimal_precision():
    odds = Base.metadata.tables["market_odds"].columns
    assert odds["observed_at"].nullable is False
    assert odds["decimal_odds"].type.precision == 12
    assert odds["decimal_odds"].type.scale == 5
