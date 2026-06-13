"""Tests for the conversation manager: why-handling, follow-up, sensitivity guard."""

from __future__ import annotations

from datetime import date

import pytest

from baseline.coach.coach import Coach
from baseline.coach.llm import MockLLM
from baseline.coach.retriever import SimpleEvidenceRetriever
from baseline.conversation.manager import ConversationManager
from baseline.domain.models import (
    Deviation,
    Goal,
    Insight,
    Sex,
    TriageRoute,
    UserProfile,
)


def _profile():
    return UserProfile(
        user_id="u1", name="Priya", age=38,
        sex=Sex.FEMALE, weight_kg=65.0, goal=Goal.SLEEP_BETTER,
    )


def _insight(message="Your sleep was 45 minutes below your usual."):
    return Insight(
        user_id="u1", date=date(2026, 6, 13),
        message=message, route=TriageRoute.COACH,
        deviations=[
            Deviation(metric="sleep_mins", value=375, median=420, z=-2.5,
                      direction="below", sustained=True, confidence="high"),
        ],
    )


def _mgr():
    coach = Coach(llm=MockLLM(), retriever=SimpleEvidenceRetriever())
    return ConversationManager(coach=coach)


def test_new_session_has_no_history():
    mgr = _mgr()
    assert mgr.history("u1") == []


def test_reply_to_daily_insight_stores_both_turns():
    mgr = _mgr()
    mgr.set_last_insight("u1", _insight(), today_summary="test day.")
    response = mgr.chat("u1", _profile(), "Thanks, why though?")
    hist = mgr.history("u1")
    assert len(hist) == 2
    assert hist[0].role == "user"
    assert hist[1].role == "coach"
    assert isinstance(response, str) and len(response) > 10


def test_why_question_mentions_the_deviation():
    mgr = _mgr()
    mgr.set_last_insight("u1", _insight(), today_summary="slept 6h15m.")
    response = mgr.chat("u1", _profile(), "why?")
    assert "sleep" in response.lower()


def test_sensitivity_guard_blocks_raw_data_requests():
    mgr = _mgr()
    mgr.set_last_insight("u1", _insight(), today_summary="test.")
    for trigger in ["show me my raw data", "give me all my metrics", "dump my full trends"]:
        response = mgr.chat("u1", _profile(), trigger)
        assert "app" in response.lower() or "private" in response.lower()
        assert "65" not in response  # weight not leaked


def test_sensitivity_guard_blocks_escalation_details_in_chat():
    mgr = _mgr()
    escalation_insight = Insight(
        user_id="u1", date=date(2026, 6, 13),
        message="It may be worth discussing with a doctor.",
        route=TriageRoute.ESCALATE,
        deviations=[
            Deviation(metric="rhr", value=78, median=58, z=3.1,
                      direction="above", sustained=True, confidence="high"),
        ],
    )
    mgr.set_last_insight("u1", escalation_insight, today_summary="test.")
    response = mgr.chat("u1", _profile(), "tell me more about the escalation")
    assert "app" in response.lower() or "private" in response.lower()


def test_free_form_question_gets_a_grounded_answer():
    mgr = _mgr()
    mgr.set_last_insight("u1", _insight(), today_summary="slept 6h15m, 8400 steps.")
    response = mgr.chat("u1", _profile(), "what should I do tonight?")
    assert isinstance(response, str) and len(response) > 20
    assert "diagnos" not in response.lower()


def test_chat_without_prior_insight_still_responds():
    mgr = _mgr()
    response = mgr.chat("u1", _profile(), "Hello, how does this work?")
    assert isinstance(response, str) and len(response) > 5
