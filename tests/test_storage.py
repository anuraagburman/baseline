"""Tests for the SQLAlchemy storage layer (SQLite now, Postgres-ready)."""

from __future__ import annotations

from datetime import date

import pytest

from baseline.domain.models import (
    Goal,
    DailyMetrics,
    Sex,
    SleepStages,
    UserProfile,
)
from baseline.storage.db import Database
from baseline.storage import repository as repo


@pytest.fixture
def db(tmp_path):
    database = Database(f"sqlite:///{tmp_path}/test.db")
    database.create_all()
    return database


def _profile(user_id="u1") -> UserProfile:
    return UserProfile(
        user_id=user_id,
        name="Pranav",
        age=36,
        sex=Sex.MALE,
        weight_kg=78.0,
        goal=Goal.LOSE_FAT,
        history_flags=["family_history_cardiac"],
    )


def _metrics(day: int) -> DailyMetrics:
    return DailyMetrics(
        date=date(2026, 6, day),
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


def test_upsert_and_get_user_roundtrips(db):
    with db.session() as s:
        repo.upsert_user(s, _profile())
    with db.session() as s:
        got = repo.get_user(s, "u1")
    assert got is not None
    assert got.goal is Goal.LOSE_FAT
    assert got.history_flags == ["family_history_cardiac"]


def test_upsert_user_updates_existing(db):
    with db.session() as s:
        repo.upsert_user(s, _profile())
    with db.session() as s:
        updated = _profile()
        updated.goal = Goal.SLEEP_BETTER
        repo.upsert_user(s, updated)
    with db.session() as s:
        got = repo.get_user(s, "u1")
    assert got.goal is Goal.SLEEP_BETTER


def test_get_unknown_user_returns_none(db):
    with db.session() as s:
        assert repo.get_user(s, "nobody") is None


def test_save_and_fetch_metrics_range_roundtrips_full_shape(db):
    with db.session() as s:
        repo.upsert_user(s, _profile())
        for d in range(1, 6):
            repo.save_daily_metrics(s, "u1", _metrics(d))
    with db.session() as s:
        got = repo.get_metrics_range(s, "u1", date(2026, 6, 2), date(2026, 6, 4))
    assert [m.date.day for m in got] == [2, 3, 4]  # inclusive, ordered
    assert got[0].sleep_stages.deep == 70  # nested structure survives round-trip


def test_save_daily_metrics_is_idempotent_per_day(db):
    with db.session() as s:
        repo.upsert_user(s, _profile())
        repo.save_daily_metrics(s, "u1", _metrics(1))
        changed = _metrics(1)
        changed.rhr = 70.0
        repo.save_daily_metrics(s, "u1", changed)  # same day -> upsert
    with db.session() as s:
        got = repo.get_recent_metrics(s, "u1", 10)
    assert len(got) == 1
    assert got[0].rhr == 70.0


def test_get_recent_metrics_returns_newest_first_limited(db):
    with db.session() as s:
        repo.upsert_user(s, _profile())
        for d in range(1, 11):
            repo.save_daily_metrics(s, "u1", _metrics(d))
    with db.session() as s:
        got = repo.get_recent_metrics(s, "u1", 3)
    assert [m.date.day for m in got] == [10, 9, 8]
