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
    MacroBreakdown,
    Meal,
    NutritionTargets,
    OnboardingState,
    UserProfile,
    WorkoutLog,
)
from baseline.storage.schema import (
    DailyMetricsRow,
    MealRow,
    NutritionTargetRow,
    OAuthTokenRow,
    OnboardingStateRow,
    OutcomeRow,
    UserBaselineRow,
    UserRow,
    WorkoutLogRow,
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
    row.profile_extra = {
        "height_cm": profile.height_cm,
        "body_measurements": profile.body_measurements,
        "workouts_per_week": profile.workouts_per_week,
        "workout_types": list(profile.workout_types),
        "health_conditions": list(profile.health_conditions),
    }
    session.flush()


def get_user(session: Session, user_id: str) -> UserProfile | None:
    row = session.get(UserRow, user_id)
    if row is None:
        return None
    extra = row.profile_extra or {}
    return UserProfile(
        user_id=row.user_id,
        name=row.name,
        age=row.age,
        sex=row.sex,
        weight_kg=row.weight_kg,
        goal=row.goal,
        history_flags=list(row.history_flags or []),
        delivery_pref=row.delivery_pref,
        height_cm=extra.get("height_cm"),
        body_measurements=extra.get("body_measurements"),
        workouts_per_week=extra.get("workouts_per_week", 0),
        workout_types=list(extra.get("workout_types") or []),
        health_conditions=list(extra.get("health_conditions") or []),
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


# --- Meals ---

def save_meal(session: Session, meal: Meal) -> None:
    """Upsert one meal (idempotent per meal id)."""
    existing = session.get(MealRow, meal.id)
    payload = meal.model_dump(mode="json")
    if existing is None:
        session.add(
            MealRow(
                id=meal.id,
                user_id=meal.user_id,
                date=meal.timestamp.date(),
                payload=payload,
            )
        )
    else:
        existing.payload = payload
        existing.date = meal.timestamp.date()
    session.flush()


def get_meals_for_day(session: Session, user_id: str, day: Date) -> list[Meal]:
    rows = session.scalars(
        select(MealRow)
        .where(MealRow.user_id == user_id, MealRow.date == day)
        .order_by(MealRow.date.asc())
    ).all()
    meals = [Meal.model_validate(r.payload) for r in rows]
    return sorted(meals, key=lambda m: m.timestamp)


# --- Nutrition targets ---

def set_nutrition_targets(
    session: Session, user_id: str, targets: NutritionTargets
) -> None:
    """Upsert the user's daily macro targets (one row per user)."""
    row = session.get(NutritionTargetRow, user_id)
    if row is None:
        row = NutritionTargetRow(user_id=user_id)
        session.add(row)
    row.kcal = targets.kcal
    row.protein_g = targets.protein_g
    row.carbs_g = targets.carbs_g
    row.fat_g = targets.fat_g
    session.flush()


def get_nutrition_targets(session: Session, user_id: str) -> NutritionTargets | None:
    row = session.get(NutritionTargetRow, user_id)
    if row is None:
        return None
    return NutritionTargets(
        kcal=row.kcal, protein_g=row.protein_g, carbs_g=row.carbs_g, fat_g=row.fat_g
    )


# --- Workouts ---

def log_workout(session: Session, workout: WorkoutLog) -> None:
    session.add(
        WorkoutLogRow(
            user_id=workout.user_id,
            date=workout.date,
            type=workout.type,
            duration_min=workout.duration_min,
            source=workout.source,
        )
    )
    session.flush()


def get_workouts_for_week(
    session: Session, user_id: str, reference: Date
) -> list[WorkoutLog]:
    """Workouts in the 7-day window ending at ``reference`` (inclusive)."""
    from datetime import timedelta

    start = reference - timedelta(days=6)
    rows = session.scalars(
        select(WorkoutLogRow)
        .where(
            WorkoutLogRow.user_id == user_id,
            WorkoutLogRow.date >= start,
            WorkoutLogRow.date <= reference,
        )
        .order_by(WorkoutLogRow.date.asc())
    ).all()
    return [
        WorkoutLog(
            user_id=r.user_id, date=r.date, type=r.type,
            duration_min=r.duration_min, source=r.source,
        )
        for r in rows
    ]


# --- Onboarding state ---

def save_onboarding_state(session: Session, state: OnboardingState) -> None:
    """Upsert onboarding state (one row per user)."""
    row = session.get(OnboardingStateRow, state.user_id)
    if row is None:
        row = OnboardingStateRow(user_id=state.user_id)
        session.add(row)
    row.step = state.step
    row.data = dict(state.data)
    row.complete = state.complete
    session.flush()


def get_onboarding_state(session: Session, user_id: str) -> OnboardingState | None:
    row = session.get(OnboardingStateRow, user_id)
    if row is None:
        return None
    return OnboardingState(
        user_id=row.user_id, step=row.step, data=dict(row.data or {}),
        complete=row.complete,
    )


# --- OAuth tokens ---

def save_oauth_tokens(
    session: Session, user_id: str, provider: str, tokens: dict
) -> None:
    row = session.get(OAuthTokenRow, (user_id, provider))
    if row is None:
        row = OAuthTokenRow(user_id=user_id, provider=provider)
        session.add(row)
    row.tokens = dict(tokens)
    session.flush()


def get_oauth_tokens(session: Session, user_id: str, provider: str) -> dict | None:
    row = session.get(OAuthTokenRow, (user_id, provider))
    return dict(row.tokens) if row is not None else None
