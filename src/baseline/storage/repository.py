"""Provider-agnostic persistence helpers.

These functions translate between domain models and ORM rows so that callers
work only in terms of :mod:`baseline.domain.models`. They never expose ORM rows.
"""

from __future__ import annotations

from datetime import date as Date

from sqlalchemy import select
from sqlalchemy.orm import Session

from baseline.domain.models import (
    DailyMetrics,
    Insight,
    UserProfile,
)
from baseline.storage.schema import (
    DailyMetricsRow,
    OutcomeRow,
    UserBaselineRow,
    UserRow,
)


# --- Users ---

def upsert_user(session: Session, profile: UserProfile) -> None:
    row = session.get(UserRow, profile.user_id)
    if row is None:
        row = UserRow(user_id=profile.user_id)
        session.add(row)
    row.name = profile.name
    row.age = profile.age
    row.sex = profile.sex.value
    row.weight_kg = profile.weight_kg
    row.goal = profile.goal.value
    row.history_flags = list(profile.history_flags)
    row.delivery_pref = profile.delivery_pref
    session.flush()


def get_user(session: Session, user_id: str) -> UserProfile | None:
    row = session.get(UserRow, user_id)
    if row is None:
        return None
    return UserProfile(
        user_id=row.user_id,
        name=row.name,
        age=row.age,
        sex=row.sex,
        weight_kg=row.weight_kg,
        goal=row.goal,
        history_flags=list(row.history_flags or []),
        delivery_pref=row.delivery_pref,
    )


# --- Daily metrics ---

def save_daily_metrics(session: Session, user_id: str, metrics: DailyMetrics) -> None:
    """Upsert one day of metrics (idempotent per ``(user_id, date)``)."""
    existing = session.scalar(
        select(DailyMetricsRow).where(
            DailyMetricsRow.user_id == user_id,
            DailyMetricsRow.date == metrics.date,
        )
    )
    payload = metrics.model_dump(mode="json")
    if existing is None:
        session.add(
            DailyMetricsRow(user_id=user_id, date=metrics.date, payload=payload)
        )
    else:
        existing.payload = payload
    session.flush()


def get_metrics_range(
    session: Session, user_id: str, start: Date, end: Date
) -> list[DailyMetrics]:
    """All metrics for ``user_id`` between ``start`` and ``end`` (inclusive), oldest first."""
    rows = session.scalars(
        select(DailyMetricsRow)
        .where(
            DailyMetricsRow.user_id == user_id,
            DailyMetricsRow.date >= start,
            DailyMetricsRow.date <= end,
        )
        .order_by(DailyMetricsRow.date.asc())
    ).all()
    return [DailyMetrics.model_validate(r.payload) for r in rows]


def get_recent_metrics(session: Session, user_id: str, n: int) -> list[DailyMetrics]:
    """The ``n`` most recent days, newest first."""
    rows = session.scalars(
        select(DailyMetricsRow)
        .where(DailyMetricsRow.user_id == user_id)
        .order_by(DailyMetricsRow.date.desc())
        .limit(n)
    ).all()
    return [DailyMetrics.model_validate(r.payload) for r in rows]


# --- Outcomes (insights + feedback loop) ---

def save_insight(session: Session, insight: Insight) -> None:
    session.add(
        OutcomeRow(
            user_id=insight.user_id,
            date=insight.date,
            route=insight.route.value,
            message=insight.message,
            deviations=[d.model_dump(mode="json") for d in insight.deviations],
            evidence_citations=list(insight.evidence_citations),
            generated_at=insight.generated_at,
        )
    )
    session.flush()


def get_insights(session: Session, user_id: str, limit: int = 30) -> list[Insight]:
    rows = session.scalars(
        select(OutcomeRow)
        .where(OutcomeRow.user_id == user_id)
        .order_by(OutcomeRow.generated_at.desc())
        .limit(limit)
    ).all()
    from baseline.domain.models import Deviation, TriageRoute

    return [
        Insight(
            user_id=r.user_id,
            date=r.date,
            message=r.message,
            route=TriageRoute(r.route),
            deviations=[Deviation.model_validate(d) for d in (r.deviations or [])],
            evidence_citations=list(r.evidence_citations or []),
            generated_at=r.generated_at,
        )
        for r in rows
    ]


def save_baseline(
    session: Session,
    user_id: str,
    metric: str,
    median: float,
    mad: float,
    window_days: int,
) -> None:
    session.add(
        UserBaselineRow(
            user_id=user_id,
            metric=metric,
            median=median,
            mad=mad,
            window_days=window_days,
        )
    )
    session.flush()
