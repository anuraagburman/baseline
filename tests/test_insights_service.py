"""Tests for the reusable daily-insight service (shared by the route + scheduler)."""

from __future__ import annotations

from datetime import date

import pytest

from baseline.coach.coach import Coach
from baseline.coach.llm import MockLLM
from baseline.coach.retriever import SimpleEvidenceRetriever
from baseline.domain.models import Goal, Insight, Sex, UserProfile
from baseline.services.insights import compute_daily_insight
from baseline.sources.synthetic import SyntheticHealthSource
from baseline.ingestion.pipeline import ingest_range
from baseline.storage import repository as repo
from baseline.storage.db import Database


@pytest.fixture
def db(tmp_path):
    database = Database(f"sqlite:///{tmp_path}/test.db")
    database.create_all()
    return database


def _coach():
    return Coach(llm=MockLLM(), retriever=SimpleEvidenceRetriever())


def _seed_user(db, user_id="u1", days=20):
    profile = UserProfile(user_id=user_id, name="Pranav", age=36, sex=Sex.MALE,
                          weight_kg=78.0, goal=Goal.LOSE_FAT)
    with db.session() as s:
        repo.upsert_user(s, profile)
    from datetime import timedelta
    today = date.today()
    ingest_range(db, SyntheticHealthSource(), user_id, today - timedelta(days=days - 1), today)
    return profile


def test_compute_daily_insight_returns_insight(db):
    _seed_user(db)
    insight = compute_daily_insight(db, _coach(), "u1")
    assert isinstance(insight, Insight)
    assert insight.user_id == "u1"
    assert insight.message
    assert insight.route.value in {"monitor", "coach", "escalate"}


def test_compute_daily_insight_persists_insight(db):
    _seed_user(db)
    compute_daily_insight(db, _coach(), "u1")
    with db.session() as s:
        saved = repo.get_insights(s, "u1", limit=5)
    assert len(saved) >= 1


def test_compute_daily_insight_unknown_user_returns_none(db):
    assert compute_daily_insight(db, _coach(), "ghost") is None


def test_compute_daily_insight_no_data_returns_none(db):
    profile = UserProfile(user_id="u2", age=30, sex=Sex.MALE, weight_kg=70.0,
                          goal=Goal.GENERAL_HEALTH)
    with db.session() as s:
        repo.upsert_user(s, profile)
    assert compute_daily_insight(db, _coach(), "u2") is None
