"""Tests for opt-in consent: persistence, list_opted_in_users, stop/pause handling."""

from __future__ import annotations

import pytest

from baseline.channels.base import InboundMessage
from baseline.coach.coach import Coach
from baseline.coach.llm import MockLLM
from baseline.coach.retriever import SimpleEvidenceRetriever
from baseline.conversation.manager import ConversationManager
from baseline.domain.models import Goal, Sex, UserProfile
from baseline.nutrition.estimator import MockNutritionEstimator
from baseline.onboarding.conversation import OnboardingFSM
from baseline.sources.synthetic import SyntheticHealthSource
from baseline.storage import repository as repo
from baseline.storage.db import Database


@pytest.fixture
def db(tmp_path):
    database = Database(f"sqlite:///{tmp_path}/test.db")
    database.create_all()
    return database


def _user(db, user_id, opted_in, delivery_pref="evening"):
    p = UserProfile(user_id=user_id, age=35, sex=Sex.MALE, weight_kg=75.0,
                    goal=Goal.LOSE_FAT, delivery_pref=delivery_pref, opted_in=opted_in)
    with db.session() as s:
        repo.upsert_user(s, p)
        from baseline.domain.models import OnboardingState
        repo.save_onboarding_state(s, OnboardingState(user_id=user_id, step="done",
                                                       data={}, complete=True))
    return p


# --- Persistence ---

def test_opted_in_persists_round_trip(db):
    _user(db, "u1", opted_in=True)
    with db.session() as s:
        got = repo.get_user(s, "u1")
    assert got.opted_in is True


def test_opted_in_defaults_false(db):
    p = UserProfile(user_id="u2", age=30, sex=Sex.MALE, weight_kg=70.0, goal=Goal.GENERAL_HEALTH)
    with db.session() as s:
        repo.upsert_user(s, p)
        got = repo.get_user(s, "u2")
    assert got.opted_in is False


# --- list_opted_in_users ---

def test_list_opted_in_users_only_returns_consented(db):
    _user(db, "yes1", opted_in=True)
    _user(db, "yes2", opted_in=True)
    _user(db, "no1", opted_in=False)
    with db.session() as s:
        opted = repo.list_opted_in_users(s)
    ids = {u.user_id for u in opted}
    assert ids == {"yes1", "yes2"}


def test_list_opted_in_users_filter_by_delivery_pref(db):
    _user(db, "morning1", opted_in=True, delivery_pref="morning")
    _user(db, "evening1", opted_in=True, delivery_pref="evening")
    _user(db, "both1", opted_in=True, delivery_pref="both")
    with db.session() as s:
        morning = {u.user_id for u in repo.list_opted_in_users(s, window="morning")}
    # "both" users receive in every window
    assert morning == {"morning1", "both1"}


# --- stop / pause handling in the router ---

def _mgr(db):
    coach = Coach(llm=MockLLM(), retriever=SimpleEvidenceRetriever())
    return ConversationManager(coach=coach, db=db, estimator=MockNutritionEstimator(),
                               onboarding_fsm=OnboardingFSM(), source=SyntheticHealthSource())


def test_stop_flips_opted_in_off(db):
    profile = _user(db, "u1", opted_in=True)
    mgr = _mgr(db)
    reply = mgr.handle(InboundMessage(user_id="u1", text="stop"), profile)
    assert "stop" in reply.lower() or "won't" in reply.lower() or "paused" in reply.lower()
    with db.session() as s:
        assert repo.get_user(s, "u1").opted_in is False


def test_pause_flips_opted_in_off(db):
    profile = _user(db, "u1", opted_in=True)
    mgr = _mgr(db)
    mgr.handle(InboundMessage(user_id="u1", text="pause"), profile)
    with db.session() as s:
        assert repo.get_user(s, "u1").opted_in is False
