"""Activity engine — summarise workouts, streaks, and steps.

A day counts as "worked out" if the user logged a workout OR the device recorded
enough active minutes. Streaks and weekly counts are computed from that combined
signal so manual logs and device data reinforce each other.
"""

from __future__ import annotations

from datetime import date as Date
from datetime import timedelta

from baseline.domain.models import (
    ActivitySummary,
    DailyMetrics,
    Goal,
    UserProfile,
    WorkoutLog,
)

_ACTIVE_MINUTES_THRESHOLD = 20  # active_zone_mins at/above this = an active day
_STEP_TARGETS = {
    Goal.LOSE_FAT: 10000,
    Goal.MORE_ENERGY: 10000,
    Goal.GENERAL_HEALTH: 8000,
    Goal.SLEEP_BETTER: 8000,
}


def _worked_out_days(
    metrics_series: list[DailyMetrics], workout_logs: list[WorkoutLog]
) -> set[Date]:
    """The set of dates the user worked out (device-active OR logged)."""
    days: set[Date] = {
        m.date for m in metrics_series if m.active_zone_mins >= _ACTIVE_MINUTES_THRESHOLD
    }
    days |= {w.date for w in workout_logs}
    return days


def summarize_activity(
    metrics_series: list[DailyMetrics],
    workout_logs: list[WorkoutLog],
    reference: Date,
) -> ActivitySummary:
    by_date = {m.date: m for m in metrics_series}
    active_days = _worked_out_days(metrics_series, workout_logs)

    # Days worked out in the trailing 7-day window.
    week = {reference - timedelta(days=i) for i in range(7)}
    days_this_week = len(active_days & week)

    # Current streak — consecutive active days ending at the reference date.
    streak = 0
    cursor = reference
    while cursor in active_days:
        streak += 1
        cursor -= timedelta(days=1)

    today = by_date.get(reference)
    steps_today = today.steps if today else 0
    active_minutes = today.active_zone_mins if today else 0

    last_7 = [by_date[reference - timedelta(days=i)] for i in range(7) if (reference - timedelta(days=i)) in by_date]
    steps_7d_avg = round(sum(m.steps for m in last_7) / len(last_7), 1) if last_7 else 0.0

    return ActivitySummary(
        days_worked_out_this_week=days_this_week,
        current_streak=streak,
        steps_today=steps_today,
        steps_7d_avg=steps_7d_avg,
        active_minutes=active_minutes,
    )


def derive_step_target(profile: UserProfile) -> int:
    """A simple daily step target driven by the user's goal."""
    return _STEP_TARGETS.get(profile.goal, 8000)
