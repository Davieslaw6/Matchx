"""Portable SQLAlchemy 2 models. Schema changes are managed only by Alembic."""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, LargeBinary, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def new_id() -> str:
    return str(uuid4())

class Base(DeclarativeBase):
    pass

class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

class AppSetting(Base, Timestamped):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

class OwnerAccount(Base, Timestamped):
    __tablename__ = "owner_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class Competition(Base, Timestamped):
    __tablename__ = "competitions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_competition_id: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str | None] = mapped_column(String(120))
    season: Mapped[str | None] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint("provider", "provider_competition_id", name="uq_competition_provider_id"),)

class Team(Base, Timestamped):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_team_id: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str | None] = mapped_column(String(120))
    __table_args__ = (UniqueConstraint("provider", "provider_team_id", name="uq_team_provider_id"),)

class TeamAlias(Base):
    __tablename__ = "team_aliases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)

class Fixture(Base, Timestamped):
    __tablename__ = "fixtures"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_fixture_id: Mapped[str] = mapped_column(String(160), nullable=False)
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id"), nullable=False, index=True)
    home_team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    away_team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    match_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    kickoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="scheduled", index=True)
    season: Mapped[str | None] = mapped_column(String(32))
    venue: Mapped[str | None] = mapped_column(String(200))
    __table_args__ = (UniqueConstraint("provider", "provider_fixture_id", name="uq_fixture_provider_id"),
                      Index("ix_fixture_comp_kickoff", "competition_id", "kickoff_at"))

class MatchResult(Base):
    __tablename__ = "match_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    fixture_id: Mapped[str] = mapped_column(ForeignKey("fixtures.id", ondelete="CASCADE"), unique=True, nullable=False)
    home_goals: Mapped[int] = mapped_column(Integer, nullable=False)
    away_goals: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class TeamStatistic(Base):
    __tablename__ = "team_statistics"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False)
    season: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint("team_id", "competition_id", "season", "as_of", name="uq_team_stat_snapshot"),)

class MarketOdds(Base):
    __tablename__ = "market_odds"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    fixture_id: Mapped[str] = mapped_column(ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    bookmaker: Mapped[str | None] = mapped_column(String(120))
    market: Mapped[str] = mapped_column(String(80), nullable=False)
    outcome: Mapped[str] = mapped_column(String(120), nullable=False)
    decimal_odds: Mapped[Decimal] = mapped_column(Numeric(12, 5), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    observed_at_precision: Mapped[str] = mapped_column(String(32), nullable=False, default="provider_timestamp")
    raw_payload_hash: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("fixture_id", "provider", "bookmaker", "market", "outcome", "observed_at",
                                       name="uq_market_odds_snapshot"),)

class Prediction(Base):
    __tablename__ = "predictions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    fixture_id: Mapped[str] = mapped_column(ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    data_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    probabilities: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    feature_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("predictions.id"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="live")
    __table_args__ = (UniqueConstraint("fixture_id", "model_version", name="uq_prediction_fixture_model"),)

class PredictionEvaluation(Base):
    __tablename__ = "prediction_evaluations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    prediction_id: Mapped[str] = mapped_column(ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False, index=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

class Ticket(Base, Timestamped):
    __tablename__ = "tickets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    notes: Mapped[str | None] = mapped_column(Text)

class TicketSelection(Base):
    __tablename__ = "ticket_selections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    fixture_id: Mapped[str] = mapped_column(ForeignKey("fixtures.id"), nullable=False)
    market: Mapped[str] = mapped_column(String(80), nullable=False)
    outcome: Mapped[str] = mapped_column(String(120), nullable=False)
    odds_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 5), nullable=False)
    bookmaker: Mapped[str | None] = mapped_column(String(120))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

class TicketRevision(Base):
    __tablename__ = "ticket_revisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str] = mapped_column(String(80), nullable=False, default="owner")
    before_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    after_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("ticket_id", "revision", name="uq_ticket_revision"),)

class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    storage_key: Mapped[str] = mapped_column(String(240), unique=True, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending_review")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class BookingCodeJob(Base):
    __tablename__ = "booking_code_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    bookmaker_id: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="submitted")
    requested_code: Mapped[str | None] = mapped_column(String(240))
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class DataSyncRun(Base):
    __tablename__ = "data_sync_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    counts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class ModelRegistry(Base):
    __tablename__ = "model_registry"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    model_type: Mapped[str] = mapped_column(String(80), nullable=False)
    hyperparameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    git_sha: Mapped[str | None] = mapped_column(String(40))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class ProviderRawPayload(Base):
    __tablename__ = "provider_raw_payloads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    data_type: Mapped[str] = mapped_column(String(80), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class ApiQuotaUsage(Base):
    __tablename__ = "api_quota_usage"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    __table_args__ = (UniqueConstraint("provider", "period_start", name="uq_provider_quota_period"),)

class ScreenshotImport(Base):
    __tablename__ = "screenshot_imports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(160), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    image_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="needs_review", index=True)
    ocr_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parsed_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    review_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class BookingCodeSelection(Base):
    __tablename__ = "booking_code_selections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("booking_code_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_selection_id: Mapped[str | None] = mapped_column(ForeignKey("ticket_selections.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
