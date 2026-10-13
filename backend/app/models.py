from datetime import datetime
from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base, UTCDateTime, utcnow


class Competition(Base):
    __tablename__ = "competitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("provider", "provider_id", name="uq_team_provider"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(30))
    provider_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(120))
    short_name: Mapped[str | None] = mapped_column(String(60))
    tla: Mapped[str | None] = mapped_column(String(10))


class Fixture(Base):
    __tablename__ = "fixtures"
    __table_args__ = (
        UniqueConstraint("provider", "provider_fixture_id", name="uq_fixture_provider"),
        UniqueConstraint("competition_id", "home_team_id", "away_team_id", "season", name="uq_fixture_identity"),
        Index("ix_fixture_comp_kickoff", "competition_id", "utc_kickoff"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(30))
    provider_fixture_id: Mapped[int] = mapped_column(Integer)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    season: Mapped[int] = mapped_column(Integer)
    matchday: Mapped[int | None] = mapped_column(Integer)
    utc_kickoff: Mapped[datetime] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(20))
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])
    competition: Mapped[Competition] = relationship()


class MatchResult(Base):
    __tablename__ = "match_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), unique=True)
    home_goals: Mapped[int] = mapped_column(Integer)
    away_goals: Mapped[int] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class TeamStatistic(Base):
    """Optional stats (xG, shots...). NULL value = unavailable, never zero-filled."""
    __tablename__ = "team_statistics"
    __table_args__ = (UniqueConstraint("team_id", "competition_id", "season", "stat_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    season: Mapped[int] = mapped_column(Integer)
    stat_name: Mapped[str] = mapped_column(String(50))
    value: Mapped[float | None] = mapped_column(Float)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ModelRegistry(Base):
    __tablename__ = "model_registry"
    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    provider: Mapped[str] = mapped_column(String(30))
    version: Mapped[str] = mapped_column(String(80), unique=True)
    trained_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    as_of: Mapped[datetime] = mapped_column(UTCDateTime)
    n_matches: Mapped[int] = mapped_column(Integer)
    params: Mapped[dict] = mapped_column(JSON)
    metrics: Mapped[dict | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (Index("ix_pred_fixture", "fixture_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"))
    model_version: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    data_cutoff: Mapped[datetime] = mapped_column(UTCDateTime)
    home_win: Mapped[float] = mapped_column(Float)
    draw: Mapped[float] = mapped_column(Float)
    away_win: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSON)


class PredictionEvaluation(Base):
    __tablename__ = "prediction_evaluations"
    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), unique=True)
    evaluated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    home_goals: Mapped[int] = mapped_column(Integer)
    away_goals: Mapped[int] = mapped_column(Integer)
    log_loss: Mapped[float] = mapped_column(Float)
    brier: Mapped[float] = mapped_column(Float)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    messages: Mapped[list["Message"]] = relationship(cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
