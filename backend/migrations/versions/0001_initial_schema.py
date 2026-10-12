"""Initial schema for private single-owner MATCH X.

This revision is intentionally frozen: subsequent model changes require new revisions.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(120), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "owner_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
    op.create_table(
        "login_attempts",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "competitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("provider_competition_id", sa.String(160), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("country", sa.String(120), nullable=True),
        sa.Column("season", sa.String(32), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "provider_competition_id", name="uq_competition_provider_id"),
    )
    op.create_table(
        "teams",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("provider_team_id", sa.String(160), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("country", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "provider_team_id", name="uq_team_provider_id"),
    )
    op.create_table(
        "team_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.String(200), nullable=False, unique=True),
    )
    op.create_index("ix_team_aliases_team_id", "team_aliases", ["team_id"])
    op.create_table(
        "fixtures",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("provider_fixture_id", sa.String(160), nullable=False),
        sa.Column("competition_id", sa.String(36), sa.ForeignKey("competitions.id"), nullable=False),
        sa.Column("home_team_id", sa.String(36), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("away_team_id", sa.String(36), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("match_date", sa.Date(), nullable=True),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("season", sa.String(32), nullable=True),
        sa.Column("venue", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "provider_fixture_id", name="uq_fixture_provider_id"),
    )
    op.create_index("ix_fixtures_competition_id", "fixtures", ["competition_id"])
    op.create_index("ix_fixtures_home_team_id", "fixtures", ["home_team_id"])
    op.create_index("ix_fixtures_away_team_id", "fixtures", ["away_team_id"])
    op.create_index("ix_fixtures_match_date", "fixtures", ["match_date"])
    op.create_index("ix_fixtures_kickoff_at", "fixtures", ["kickoff_at"])
    op.create_index("ix_fixtures_status", "fixtures", ["status"])
    op.create_index("ix_fixture_comp_kickoff", "fixtures", ["competition_id", "kickoff_at"])
    op.create_table(
        "match_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("fixture_id", sa.String(36), sa.ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("home_goals", sa.Integer(), nullable=False),
        sa.Column("away_goals", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "team_statistics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competition_id", sa.String(36), sa.ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season", sa.String(32), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.UniqueConstraint("team_id", "competition_id", "season", "as_of", name="uq_team_stat_snapshot"),
    )
    op.create_index("ix_team_statistics_team_id", "team_statistics", ["team_id"])
    op.create_table(
        "market_odds",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("fixture_id", sa.String(36), sa.ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("bookmaker", sa.String(120), nullable=True),
        sa.Column("market", sa.String(80), nullable=False),
        sa.Column("outcome", sa.String(120), nullable=False),
        sa.Column("decimal_odds", sa.Numeric(12, 5), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload_hash", sa.String(64), nullable=True),
    )
    op.create_index("ix_market_odds_fixture_id", "market_odds", ["fixture_id"])
    op.create_index("ix_market_odds_observed_at", "market_odds", ["observed_at"])
    op.create_table(
        "predictions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("fixture_id", sa.String(36), sa.ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_version", sa.String(80), nullable=False),
        sa.Column("data_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("probabilities", sa.JSON(), nullable=False),
        sa.Column("feature_snapshot", sa.JSON(), nullable=False),
        sa.Column("supersedes_id", sa.String(36), sa.ForeignKey("predictions.id"), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.UniqueConstraint("fixture_id", "model_version", name="uq_prediction_fixture_model"),
    )
    op.create_index("ix_predictions_fixture_id", "predictions", ["fixture_id"])
    op.create_table(
        "prediction_evaluations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("prediction_id", sa.String(36), sa.ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
    )
    op.create_index("ix_prediction_evaluations_prediction_id", "prediction_evaluations", ["prediction_id"])
    op.create_table(
        "tickets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ticket_selections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ticket_id", sa.String(36), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fixture_id", sa.String(36), sa.ForeignKey("fixtures.id"), nullable=False),
        sa.Column("market", sa.String(80), nullable=False),
        sa.Column("outcome", sa.String(120), nullable=False),
        sa.Column("odds_snapshot", sa.Numeric(12, 5), nullable=False),
        sa.Column("bookmaker", sa.String(120), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_ticket_selections_ticket_id", "ticket_selections", ["ticket_id"])
    op.create_table(
        "ticket_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ticket_id", sa.String(36), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("before_state", sa.JSON(), nullable=False),
        sa.Column("after_state", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("ticket_id", "revision", name="uq_ticket_revision"),
    )
    op.create_index("ix_ticket_revisions_ticket_id", "ticket_revisions", ["ticket_id"])
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_table(
        "uploaded_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("storage_key", sa.String(240), nullable=False, unique=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(80), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_uploaded_files_content_hash", "uploaded_files", ["content_hash"])
    op.create_table(
        "booking_code_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("bookmaker_id", sa.String(100), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("requested_code", sa.String(240), nullable=True),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "booking_code_selections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("booking_code_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticket_selection_id", sa.String(36), sa.ForeignKey("ticket_selections.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
    )
    op.create_index("ix_booking_code_selections_job_id", "booking_code_selections", ["job_id"])
    op.create_table(
        "data_sync_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_name", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(80), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_data_sync_runs_job_name", "data_sync_runs", ["job_name"])
    op.create_table(
        "model_registry",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(80), nullable=False, unique=True),
        sa.Column("model_type", sa.String(80), nullable=False),
        sa.Column("hyperparameters", sa.JSON(), nullable=False),
        sa.Column("data_hash", sa.String(64), nullable=False),
        sa.Column("git_sha", sa.String(40), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(160), primary_key=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "provider_raw_payloads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("data_type", sa.String(80), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "api_quota_usage",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calls", sa.Integer(), nullable=False),
        sa.UniqueConstraint("provider", "period_start", name="uq_provider_quota_period"),
    )

def downgrade() -> None:
    op.drop_table("api_quota_usage")
    op.drop_table("provider_raw_payloads")
    op.drop_table("idempotency_keys")
    op.drop_table("model_registry")
    op.drop_index("ix_data_sync_runs_job_name", table_name="data_sync_runs")
    op.drop_table("data_sync_runs")
    op.drop_index("ix_booking_code_selections_job_id", table_name="booking_code_selections")
    op.drop_table("booking_code_selections")
    op.drop_table("booking_code_jobs")
    op.drop_index("ix_uploaded_files_content_hash", table_name="uploaded_files")
    op.drop_table("uploaded_files")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_index("ix_ticket_revisions_ticket_id", table_name="ticket_revisions")
    op.drop_table("ticket_revisions")
    op.drop_index("ix_ticket_selections_ticket_id", table_name="ticket_selections")
    op.drop_table("ticket_selections")
    op.drop_table("tickets")
    op.drop_index("ix_prediction_evaluations_prediction_id", table_name="prediction_evaluations")
    op.drop_table("prediction_evaluations")
    op.drop_index("ix_predictions_fixture_id", table_name="predictions")
    op.drop_table("predictions")
    op.drop_index("ix_market_odds_observed_at", table_name="market_odds")
    op.drop_index("ix_market_odds_fixture_id", table_name="market_odds")
    op.drop_table("market_odds")
    op.drop_index("ix_team_statistics_team_id", table_name="team_statistics")
    op.drop_table("team_statistics")
    op.drop_table("match_results")
    op.drop_index("ix_fixture_comp_kickoff", table_name="fixtures")
    op.drop_index("ix_fixtures_status", table_name="fixtures")
    op.drop_index("ix_fixtures_kickoff_at", table_name="fixtures")
    op.drop_index("ix_fixtures_match_date", table_name="fixtures")
    op.drop_index("ix_fixtures_away_team_id", table_name="fixtures")
    op.drop_index("ix_fixtures_home_team_id", table_name="fixtures")
    op.drop_index("ix_fixtures_competition_id", table_name="fixtures")
    op.drop_table("fixtures")
    op.drop_index("ix_team_aliases_team_id", table_name="team_aliases")
    op.drop_table("team_aliases")
    op.drop_table("teams")
    op.drop_table("competitions")
    op.drop_table("login_attempts")
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("owner_accounts")
    op.drop_table("app_settings")
