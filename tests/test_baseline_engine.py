"""Tests for the personal-baseline / deviation engine.

Series are crafted so the robust z-score is hand-computable:
robust z = 0.6745 * (value - median) / MAD, where MAD = median(|x - median|).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from baseline.analytics.baseline_engine import BaselineConfig, compute_deviations
from baseline.domain.models import (
    Goal,
    DailyMetrics,
    Sex,
    SleepStages,
    UserProfile,
)

CFG = BaselineConfig(window_days=28, min_history_days=5)


def _series(rhr_values: list[float]) -> list[DailyMetrics]:
    """Build a day series varying only RHR; all other metrics held constant."""
    start = date(2026, 6, 1)
    out = []
    for i, rhr in enumerate(rhr_values):
        out.append(
            DailyMetrics(
                date=start + timedelta(days=i),
                rhr=rhr,
                hrv=65.0,
                sleep_mins=420,
                sleep_stages=SleepStages(deep=70, rem=100, light=250),
                spo2=97.0,
                resp_rate=14.0,
                steps=8400,
                active_zone_mins=30,
                calories_out=2400.0,
            )
        )
    return out


def _dev(deviations, metric):
    return next(d for d in deviations if d.metric == metric)


def test_constant_metric_has_zero_z_and_normal_direction():
    devs = compute_deviations(_series([58.0] * 10), config=CFG)
    assert _dev(devs, "hrv").z == 0.0
    assert _dev(devs, "hrv").direction == "normal"


def test_elevated_metric_gives_expected_positive_robust_z():
    # history median 58, MAD 2; today 64 -> z = 0.6745 * 6 / 2 = 2.0235
    series = _series([55, 56, 57, 58, 59, 60, 61, 64])
    dev = _dev(compute_deviations(series, config=CFG), "rhr")
    assert dev.direction == "above"
    assert dev.z == pytest.approx(2.0235, abs=1e-3)


def test_depressed_metric_gives_negative_z_and_below():
    series = _series([60, 59, 58, 57, 56, 55, 54, 50])
    dev = _dev(compute_deviations(series, config=CFG), "rhr")
    assert dev.direction == "below"
    assert dev.z < 0


def test_single_spike_is_not_marked_sustained():
    series = _series([55, 56, 57, 58, 59, 60, 61, 64])  # only the last day jumps
    assert _dev(compute_deviations(series, config=CFG), "rhr").sustained is False


def test_multi_day_elevation_is_marked_sustained():
    series = _series([57, 57, 58, 58, 62, 63, 64])  # a rising recent run
    assert _dev(compute_deviations(series, config=CFG), "rhr").sustained is True


def test_cold_start_history_is_low_confidence():
    devs = compute_deviations(_series([58, 59, 57]), config=CFG)  # < min_history_days
    assert all(d.confidence == "low" for d in devs)


def test_mature_history_is_high_confidence():
    devs = compute_deviations(_series([58] * 10), config=CFG)
    assert all(d.confidence == "high" for d in devs)


def test_cold_start_with_profile_still_flags_an_extreme_value():
    profile = UserProfile(
        user_id="u1", age=36, sex=Sex.MALE, weight_kg=78.0, goal=Goal.GENERAL_HEALTH
    )
    # essentially no personal history, but an obviously high RHR
    series = _series([110.0])
    dev = _dev(compute_deviations(series, profile=profile, config=CFG), "rhr")
    assert dev.direction == "above"
    assert dev.confidence == "low"
    assert dev.abs_z > 2  # population norm catches it
