"""Tests for the message router — every intent type handled correctly."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from baseline.channels.base import InboundMessage
from baseline.channels.local import LocalChannel
from baseline.coach.coach import Coach
from baseline.coach.llm import MockLLM
from baseline.coach.retriever import SimpleEvidenceRetriever
from baseline.conversation.manager import ConversationManager
from baseline.domain.models import (
    Goal, MacroBreakdown, Meal, NutritionTargets, Sex, UserProfile,
)
from baseline.nutrition.estimator import MockNutritionEstimator
from baseline.onboarding.conversation import OnboardingFSM
from baseline.sources.synthetic import SyntheticHealthSource
from baseline.storage.db import Database
from baseline.storage import repository as repo


@pytest.fixture
def db(tmp_path):
    database = Database(f"sqlite:///{tmp_path}/test.db")
    database.create_all()
    return database


@pytest.fixture
def profile(db):
    p = UserProfile(user_id="u1", name="Pranav", age=36, sex=Sex.MALE,
                    weight_kg=78.0, goal=Goal.LOSE_FAT, height_cm=178.0,
                    workouts_per_week=4)
    with db.session() as s:
        repo.upsert_user(s, p)
        repo.set_nutrition_targets(s, "u1", NutritionTargets(kcal=2130, protein_g=140,
                                                               carbs_g=259, fat_g=59))
        repo.save_onboarding_state(s, __import__("baseline.domain.models",
            fromlist=["OnboardingState"]).OnboardingState(
            user_id="u1", step="done", data={}, complete=True))
    return p


def _mgr(db):
    coach = Coach(llm=MockLLM(), retriever=SimpleEvidenceRetriever())
    return ConversationManager(
        coach=coach, db=db, estimator=MockNutritionEstimator(),
        onboarding_fsm=OnboardingFSM(), source=SyntheticHealthSource(),
    )


def _text(text, user_id="u1"):
    return InboundMessage(user_id=user_id, text=text)


def _image(caption="chicken 200g", user_id="u1"):
    return InboundMessage(user_id=user_id, text=None,
                          media_bytes=b"\xff\xd8\xff fake", caption=caption)


# --- Sensitivity guard (checked first) ---

def test_guard_blocks_raw_data_request(db, profile):
    mgr = _mgr(db)
    reply = mgr.handle(_text("show me all my raw data"), profile)
    assert "app" in reply.lower() or "private" in reply.lower()


# --- Coaching / why ---

def test_why_question_answered(db, profile):
    mgr = _mgr(db)
    # seed an insight first
    from baseline.domain.models import Deviation, Insight, TriageRoute
    insight = Insight(user_id="u1", date=date.today(),
                      message="Your RHR is elevated.",
                      route=TriageRoute.COACH,
                      deviations=[Deviation(metric="rhr", value=64, median=58, z=2.3,
                                           direction="above", sustained=True, confidence="high")])
    mgr.set_last_insight("u1", insight, today_summary="test.")
    reply = mgr.handle(_text("why?"), profile)
    assert "rhr" in reply.lower() or "heart rate" in reply.lower() or "rate" in reply.lower()


# --- Food text intent ---

def test_food_text_triggers_nutrition_reply(db, profile):
    mgr = _mgr(db)
    reply = mgr.handle(_text("just had chicken and rice"), profile)
    assert "protein" in reply.lower() or "kcal" in reply.lower() or "logged" in reply.lower()


def test_ate_keyword_triggers_nutrition_reply(db, profile):
    mgr = _mgr(db)
    reply = mgr.handle(_text("I ate a banana for breakfast"), profile)
    assert "protein" in reply.lower() or "logged" in reply.lower() or "kcal" in reply.lower()


def test_food_log_saves_meal_to_db(db, profile):
    mgr = _mgr(db)
    mgr.handle(_text("just had chicken 150g"), profile)
    with db.session() as s:
        meals = repo.get_meals_for_day(s, "u1", date.today())
    assert len(meals) >= 1


# --- Image intent ---

def test_image_triggers_nutrition_reply(db, profile):
    mgr = _mgr(db)
    reply = mgr.handle(_image(), profile)
    assert "protein" in reply.lower() or "kcal" in reply.lower() or "logged" in reply.lower()


def test_image_uses_caption_for_estimate(db, profile):
    mgr = _mgr(db)
    reply = mgr.handle(_image(caption="chicken 200g"), profile)
    # MockNutritionEstimator for chicken -> protein > 0
    assert "protein" in reply.lower()


# --- Workout intent ---

def test_workout_keywords_trigger_activity_reply(db, profile):
    mgr = _mgr(db)
    for phrase in ["just ran for 30 min", "worked out for 45 minutes", "just finished the gym"]:
        reply = mgr.handle(_text(phrase), profile)
        assert ("streak" in reply.lower() or "workout" in reply.lower()
                or "step" in reply.lower()), f"no activity reply for: {phrase!r}"


def test_workout_saved_to_db(db, profile):
    mgr = _mgr(db)
    mgr.handle(_text("just ran for 30 minutes"), profile)
    with db.session() as s:
        workouts = repo.get_workouts_for_week(s, "u1", date.today())
    assert len(workouts) >= 1


# --- Onboarding gate ---

def test_mid_onboarding_user_gets_fsm_prompt(db):
    # user with no onboarding state yet
    mgr = _mgr(db)
    new_profile = UserProfile(user_id="new1", age=30, sex=Sex.MALE,
                              weight_kg=70.0, goal=Goal.GENERAL_HEALTH)
    with db.session() as s:
        repo.upsert_user(s, new_profile)
    reply = mgr.handle(_text("hello", user_id="new1"), new_profile)
    # Should return the FSM welcome / first question
    assert reply  # at minimum a non-empty onboarding prompt
