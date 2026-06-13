"""Tests for the onboarding flow: backfill, profile persistence, first insight."""

from __future__ import annotations

import pytest

from baseline.coach.coach import Coach
from baseline.coach.llm import MockLLM
from baseline.coach.retriever import SimpleEvidenceRetriever
from baseline.domain.models import Goal, Sex, UserProfile
from baseline.onboarding.flow import OnboardingRequest, onboard_user
from baseline.sources.synthetic import SyntheticHealthSource
from baseline.storage import repository as repo
from baseline.storage.db import Database


@pytest.fixture
def db(tmp_path):
    database = Database(f"sqlite:///{tmp_path}/test.db")
    database.create_all()
    return database


def _request(goal=Goal.LOSE_FAT, backfill_days=10):
    return OnboardingRequest(
        user_id="u1",
        name="Pranav",
        age=36,
        sex=Sex.MALE,
        weight_kg=78.0,
        goal=goal,
        delivery_pref="evening",
        backfill_days=backfill_days,
    )


def _coach():
    return Coach(llm=MockLLM(), retriever=SimpleEvidenceRetriever())


def test_onboard_persists_user_profile(db):
    result = onboard_user(db, SyntheticHealthSource(), _coach(), _request())
    with db.session() as s:
        profile = repo.get_user(s, "u1")
    assert profile is not None
    assert profile.goal is Goal.LOSE_FAT
    assert profile.age == 36


def test_onboard_backfills_correct_number_of_days(db):
    onboard_user(db, SyntheticHealthSource(), _coach(), _request(backfill_days=10))
    with db.session() as s:
        got = repo.get_recent_metrics(s, "u1", 50)
    assert len(got) == 10


def test_onboard_returns_a_first_value_insight(db):
    result = onboard_user(db, SyntheticHealthSource(), _coach(), _request())
    assert result.first_insight is not None
    assert result.first_insight.user_id == "u1"
    assert result.first_insight.message


def test_first_insight_message_is_not_empty_even_with_cold_start(db):
    # Only 3 days — below min_history_days; cold-start path.
    result = onboard_user(db, SyntheticHealthSource(), _coach(), _request(backfill_days=3))
    assert result.first_insight.message.strip()


def test_onboard_is_idempotent(db):
    """Onboarding the same user twice should not duplicate rows."""
    onboard_user(db, SyntheticHealthSource(), _coach(), _request())
    onboard_user(db, SyntheticHealthSource(), _coach(), _request())
    with db.session() as s:
        got = repo.get_recent_metrics(s, "u1", 100)
    assert len(got) == 10  # not 20
