"""Tests for the ingestion pipeline (source -> normalise -> persist)."""

from __future__ import annotations

from datetime import date

import pytest

from baseline.domain.models import Goal, Sex, UserProfile
from baseline.ingestion.pipeline import ingest_day, ingest_range
from baseline.sources.synthetic import SyntheticHealthSource
from baseline.storage import repository as repo
from baseline.storage.db import Database


@pytest.fixture
def db(tmp_path):
    database = Database(f"sqlite:///{tmp_path}/test.db")
    database.create_all()
    with database.session() as s:
        repo.upsert_user(
            s,
            UserProfile(
                user_id="u1", age=36, sex=Sex.MALE, weight_kg=78.0, goal=Goal.LOSE_FAT
            ),
        )
    return database


def test_ingest_day_persists_one_day(db):
    src = SyntheticHealthSource()
    count = ingest_day(db, src, "u1", date(2026, 6, 1))
    assert count == 1
    with db.session() as s:
        got = repo.get_recent_metrics(s, "u1", 10)
    assert len(got) == 1
    assert got[0].date == date(2026, 6, 1)


def test_ingest_range_persists_every_day_inclusive(db):
    src = SyntheticHealthSource()
    count = ingest_range(db, src, "u1", date(2026, 6, 1), date(2026, 6, 10))
    assert count == 10
    with db.session() as s:
        got = repo.get_recent_metrics(s, "u1", 100)
    assert len(got) == 10


def test_ingest_is_idempotent_per_day(db):
    src = SyntheticHealthSource()
    ingest_range(db, src, "u1", date(2026, 6, 1), date(2026, 6, 5))
    ingest_range(db, src, "u1", date(2026, 6, 3), date(2026, 6, 7))  # overlaps
    with db.session() as s:
        got = repo.get_recent_metrics(s, "u1", 100)
    assert len(got) == 7  # days 1..7, no duplicates
