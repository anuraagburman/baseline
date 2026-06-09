"""Tests for the source-abstraction layer and the synthetic generator."""

from __future__ import annotations

from datetime import date, timedelta

from baseline.domain.models import DailyMetrics
from baseline.sources.base import HealthSource
from baseline.sources.synthetic import SyntheticHealthSource


def test_synthetic_source_satisfies_protocol():
    src = SyntheticHealthSource()
    assert isinstance(src, HealthSource)


def test_fetch_day_returns_metrics_in_realistic_ranges():
    src = SyntheticHealthSource()
    m = src.fetch_day("u1", date(2026, 6, 1))
    assert isinstance(m, DailyMetrics)
    assert 40 <= m.rhr <= 90
    assert 15 <= m.hrv <= 140
    assert 3 * 60 <= m.sleep_mins <= 10 * 60
    assert 90 <= m.spo2 <= 100
    assert 1000 <= m.steps <= 25000


def test_fetch_day_is_deterministic_per_user_and_date():
    a = SyntheticHealthSource().fetch_day("u1", date(2026, 6, 1))
    b = SyntheticHealthSource().fetch_day("u1", date(2026, 6, 1))
    assert a == b


def test_different_users_have_different_baselines():
    a = SyntheticHealthSource().fetch_day("u1", date(2026, 6, 1))
    b = SyntheticHealthSource().fetch_day("u2", date(2026, 6, 1))
    assert a != b  # seeded per user; their day-profiles differ


def test_sleep_stages_sum_to_sleep_minutes():
    m = SyntheticHealthSource().fetch_day("u1", date(2026, 6, 1))
    stages = m.sleep_stages
    assert stages.deep + stages.rem + stages.light == m.sleep_mins


def test_fetch_range_returns_consecutive_inclusive_days_oldest_first():
    src = SyntheticHealthSource()
    end = date(2026, 6, 10)
    start = end - timedelta(days=4)
    days = src.fetch_range("u1", start, end)
    assert [d.date for d in days] == [start + timedelta(days=i) for i in range(5)]


def test_anomaly_overlay_shifts_the_targeted_metric_on_that_day():
    day = date(2026, 6, 10)
    base = SyntheticHealthSource().fetch_day("u1", day)
    anomalous = SyntheticHealthSource(anomalies={day: {"rhr": 8.0}}).fetch_day("u1", day)
    assert anomalous.rhr == base.rhr + 8.0
    # untouched metrics are unchanged
    assert anomalous.hrv == base.hrv
