"""Tests for the provider-agnostic domain models."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from baseline.domain.models import (
    Deviation,
    DailyMetrics,
    Goal,
    Sex,
    SleepStages,
    TriageRoute,
    UserProfile,
)


def _metrics(**overrides) -> DailyMetrics:
    base = dict(
        date=date(2026, 6, 1),
        rhr=58.0,
        hrv=65.0,
        sleep_mins=420,
        sleep_stages=SleepStages(deep=70, rem=100, light=250),
        spo2=97.0,
        resp_rate=14.0,
        steps=8400,
        active_zone_mins=30,
        calories_out=2400,
    )
    base.update(overrides)
    return DailyMetrics(**base)


def test_daily_metrics_constructs_with_required_fields():
    m = _metrics()
    assert m.rhr == 58.0
    assert m.sleep_stages.deep == 70
    assert m.vo2max is None  # optional


def test_daily_metrics_rejects_missing_required_field():
    with pytest.raises(ValidationError):
        DailyMetrics(date=date(2026, 6, 1))  # missing rhr, hrv, etc.


def test_daily_metrics_summary_is_plain_language_with_key_numbers():
    summary = _metrics().summary()
    assert "8400" in summary or "8,400" in summary
    # ~7h of sleep rendered in human terms
    assert "7h" in summary or "7 h" in summary or "420" in summary
    assert "58" in summary  # resting heart rate
    assert "doctor" not in summary.lower()  # no medical framing in a raw summary


def test_deviation_describe_uses_deviation_framing():
    dev = Deviation(
        metric="rhr",
        value=64.0,
        median=58.0,
        z=2.4,
        direction="above",
        sustained=True,
        confidence="high",
    )
    text = dev.describe()
    assert "6" in text  # 64 - 58 = 6 above usual
    assert "above" in text.lower()
    assert "usual" in text.lower()


def test_deviation_direction_must_be_valid():
    with pytest.raises(ValidationError):
        Deviation(
            metric="rhr",
            value=64.0,
            median=58.0,
            z=2.4,
            direction="sideways",  # invalid
            sustained=True,
            confidence="high",
        )


def test_goal_enum_has_four_v1_goals():
    assert {g.value for g in Goal} == {
        "lose_fat",
        "sleep_better",
        "more_energy",
        "general_health",
    }


def test_triage_route_enum_values():
    assert {r.value for r in TriageRoute} == {"monitor", "coach", "escalate"}


def test_user_profile_constructs():
    p = UserProfile(
        user_id="u1",
        age=36,
        sex=Sex.MALE,
        weight_kg=78.0,
        goal=Goal.LOSE_FAT,
        history_flags=["family_history_cardiac"],
    )
    assert p.goal is Goal.LOSE_FAT
    assert "family_history_cardiac" in p.history_flags
