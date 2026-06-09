"""SQLAlchemy ORM schema.

Scalars that we query/range over (date, user_id) are real columns; the rich,
provider-agnostic shapes (DailyMetrics, deviations) are stored as JSON so the
round-trip is loss-free and the schema does not have to track every wearable
field. This keeps the model the single source of truth.
"""

from __future__ import annotations

from datetime import date as Date
from datetime import datetime

from sqlalchemy import JSON, Date as SADate, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from baseline.util import utcnow


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    age: Mapped[int]
    sex: Mapped[str] = mapped_column(String)
    weight_kg: Mapped[float] = mapped_column(Float)
    goal: Mapped[str] = mapped_column(String)
    history_flags: Mapped[list] = mapped_column(JSON, default=list)
    delivery_pref: Mapped[str] = mapped_column(String, default="evening")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DailyMetricsRow(Base):
    __tablename__ = "daily_metrics"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_user_day"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    date: Mapped[Date] = mapped_column(SADate, index=True)
    payload: Mapped[dict] = mapped_column(JSON)  # full DailyMetrics, JSON-encoded


class UserBaselineRow(Base):
    __tablename__ = "user_baselines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    metric: Mapped[str] = mapped_column(String)
    median: Mapped[float] = mapped_column(Float)
    mad: Mapped[float] = mapped_column(Float)
    window_days: Mapped[int]
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OutcomeRow(Base):
    """A persisted Insight plus any feedback — the coaching feedback loop."""

    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    date: Mapped[Date] = mapped_column(SADate, index=True)
    route: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(String)
    deviations: Mapped[list] = mapped_column(JSON, default=list)
    evidence_citations: Mapped[list] = mapped_column(JSON, default=list)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
