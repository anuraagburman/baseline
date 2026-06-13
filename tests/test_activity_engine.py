"""Tests for the activity engine: streaks, days worked out, steps, step target."""

from __future__ import annotations

from datetime import date, timedelta

from baseline.analytics.activity import derive_step_target, summarize_activity
from baseline.domain.models import (
    DailyMetrics,
    Goal,
    Sex,
    SleepStages,
    UserProfile,
    WorkoutLog,
)

REF = date(2026, 6, 13)


def _day(d: date, *, steps=8000, active=10) -> DailyMetrics:
    return DailyMetrics(
        date=d, rhr=58, hrv=65, sleep_mins=420,
        sleep_stages=SleepStages(deep=70, rem=100, light=250),
        spo2=97, resp_rate=14, steps=steps, active_zone_mins=active, calories_out=2400,
    )


def _series(days: int, **kw) -> list[DailyMetrics]:
    start = REF - timedelta(days=days - 1)
    return [_day(start + timedelta(days=i), **kw) for i in range(days)]


def _workout(d: date, type="running") -> WorkoutLog:
    return WorkoutLog(user_id="u1", date=d, type=type, duration_min=30)


def test_steps_today_and_7d_average():
    series = _series(7, steps=7000)
    series[-1] = _day(REF, steps=10000)
    summary = summarize_activity(series, [], REF)
    assert summary.steps_today == 10000
    # six days at 7000 + one at 10000 = 52000 / 7
    assert summary.steps_7d_avg == round(52000 / 7, 1)


def test_active_minutes_is_todays_value():
    series = _series(3)
    series[-1] = _day(REF, active=42)
    assert summarize_activity(series, [], REF).active_minutes == 42


def test_days_worked_out_counts_logged_workouts_in_week():
    series = _series(7, active=5)  # below the active threshold
    logs = [_workout(REF), _workout(REF - timedelta(days=2))]
    assert summarize_activity(series, logs, REF).days_worked_out_this_week == 2


def test_active_minutes_threshold_counts_as_a_worked_out_day():
    series = _series(7, active=5)
    series[-1] = _day(REF, active=40)  # high active minutes, no log
    assert summarize_activity(series, [], REF).days_worked_out_this_week == 1


def test_workout_log_and_active_day_on_same_date_not_double_counted():
    series = _series(7, active=5)
    series[-1] = _day(REF, active=40)
    logs = [_workout(REF)]  # same day as the active day
    assert summarize_activity(series, logs, REF).days_worked_out_this_week == 1


def test_current_streak_counts_consecutive_days_ending_today():
    series = _series(7, active=5)
    logs = [_workout(REF), _workout(REF - timedelta(days=1)), _workout(REF - timedelta(days=2))]
    assert summarize_activity(series, logs, REF).current_streak == 3


def test_streak_is_zero_when_not_worked_out_today():
    series = _series(7, active=5)
    logs = [_workout(REF - timedelta(days=1)), _workout(REF - timedelta(days=2))]
    assert summarize_activity(series, logs, REF).current_streak == 0


def test_streak_breaks_on_a_gap():
    series = _series(7, active=5)
    logs = [_workout(REF), _workout(REF - timedelta(days=1)),
            # gap at day -2
            _workout(REF - timedelta(days=3))]
    assert summarize_activity(series, logs, REF).current_streak == 2


def test_step_target_higher_for_fat_loss_and_energy():
    p = UserProfile(user_id="u1", age=30, sex=Sex.MALE, weight_kg=78, goal=Goal.LOSE_FAT)
    assert derive_step_target(p) >= 10000
    p.goal = Goal.GENERAL_HEALTH
    assert derive_step_target(p) == 8000
