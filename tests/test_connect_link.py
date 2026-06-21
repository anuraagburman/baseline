"""The onboarding 'connect' step must emit a real, tappable Google OAuth URL."""

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
from baseline.sources.oauth import MockOAuthProvider
from baseline.sources.synthetic import SyntheticHealthSource
from baseline.storage import repository as repo
from baseline.storage.db import Database


@pytest.fixture
def db(tmp_path):
    database = Database(f"sqlite:///{tmp_path}/test.db")
    database.create_all()
    return database


def _mgr(db):
    coach = Coach(llm=MockLLM(), retriever=SimpleEvidenceRetriever())
    return ConversationManager(
        coach=coach, db=db, estimator=MockNutritionEstimator(),
        onboarding_fsm=OnboardingFSM(), source=SyntheticHealthSource(),
        oauth_provider=MockOAuthProvider(),
        public_base_url="https://baseline.example.com",
    )


def test_connect_step_emits_oauth_url(db):
    mgr = _mgr(db)
    profile = UserProfile(user_id="u1", age=30, sex=Sex.MALE, weight_kg=70.0,
                          goal=Goal.GENERAL_HEALTH)
    with db.session() as s:
        repo.upsert_user(s, profile)

    # First message kicks off onboarding (welcome + name prompt); then the answers.
    answers = ["hi", "Pranav", "36", "male", "78 kg", "178 cm", "skip", "4",
               "strength", "none", "lose fat"]  # after 'goal' the next step is 'connect'
    reply = ""
    for a in answers:
        reply = mgr.handle(InboundMessage(user_id="u1", text=a), profile)

    # The connect prompt should now include a real tappable URL.
    assert "http" in reply
    assert "u1" in reply  # MockOAuthProvider encodes user_id in the state param
