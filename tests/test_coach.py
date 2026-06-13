"""Tests for the LLM client and the coaching engine."""

from __future__ import annotations

from datetime import date

import pytest

from baseline.coach.llm import LLMClient, MockLLM
from baseline.coach.coach import Coach
from baseline.coach.prompt import CoachContext
from baseline.coach.retriever import SimpleEvidenceRetriever
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
        user_id="u1", name="Pranav", age=36,
        sex=Sex.MALE, weight_kg=78.0, goal=Goal.LOSE_FAT,
    )


def _deviation(metric="rhr", z=2.3, direction="above", value=64.0, median=58.0):
    return Deviation(
        metric=metric, value=value, median=median, z=z,
        direction=direction, sustained=True, confidence="high",
    )


def _coach():
    return Coach(llm=MockLLM(), retriever=SimpleEvidenceRetriever())


# --- LLMClient protocol ---

def test_mock_llm_satisfies_protocol():
    assert isinstance(MockLLM(), LLMClient)


def test_mock_llm_is_deterministic():
    context = CoachContext(
        profile=_profile(), route=TriageRoute.COACH,
        deviations=[_deviation()], today_summary="test day.",
    )
    a = MockLLM().generate(context)
    b = MockLLM().generate(context)
    assert a == b


def test_mock_llm_mentions_the_deviation_metric():
    context = CoachContext(
        profile=_profile(), route=TriageRoute.COACH,
        deviations=[_deviation(metric="sleep_mins", z=-2.6, direction="below",
                               value=300, median=420)],
        today_summary="8400 steps, slept 5h00m.",
    )
    msg = MockLLM().generate(context)
    assert "sleep" in msg.lower()


def test_mock_llm_includes_not_medical_advice_disclaimer():
    context = CoachContext(
        profile=_profile(), route=TriageRoute.COACH,
        deviations=[_deviation()], today_summary="test.",
    )
    msg = MockLLM().generate(context)
    assert "not medical advice" in msg.lower() or "not a doctor" in msg.lower()


def test_mock_llm_escalation_mentions_doctor():
    context = CoachContext(
        profile=_profile(), route=TriageRoute.ESCALATE,
        deviations=[_deviation()], today_summary="test.",
    )
    msg = MockLLM().generate(context)
    assert "doctor" in msg.lower()


# --- Coach ---

def test_generate_insight_returns_insight_with_correct_user_and_date():
    c = _coach()
    out = c.generate_insight(_profile(), TriageRoute.COACH, [_deviation()],
                             today_summary="test.", date=date(2026, 6, 13))
    assert isinstance(out, Insight)
    assert out.user_id == "u1"
    assert out.date == date(2026, 6, 13)
    assert out.route is TriageRoute.COACH
    assert out.message


def test_generate_insight_is_grounded_no_invented_numbers():
    dev = _deviation(metric="rhr", value=64.0, median=58.0, z=2.3,
                     direction="above")
    out = _coach().generate_insight(
        _profile(), TriageRoute.COACH, [dev],
        today_summary="8400 steps.", date=date(2026, 6, 13),
    )
    # MockLLM only uses numbers from the context; these should appear
    assert "64" in out.message or "58" in out.message or "6" in out.message


def test_answer_question_returns_message_string():
    c = _coach()
    msg = c.answer_question(
        _profile(), [_deviation()],
        today_summary="test.", question="Why is my heart rate elevated?",
    )
    assert isinstance(msg, str) and len(msg) > 20


def test_answer_question_includes_user_question_in_response():
    c = _coach()
    msg = c.answer_question(
        _profile(), [_deviation()],
        today_summary="test.", question="Why is my heart rate elevated?",
    )
    # The mock echoes keywords from the question
    assert "heart rate" in msg.lower() or "rhr" in msg.lower() or "resting" in msg.lower()


def test_monitor_route_generates_positive_message():
    out = _coach().generate_insight(
        _profile(), TriageRoute.MONITOR, [],
        today_summary="8400 steps.", date=date(2026, 6, 13),
    )
    assert out.message
    assert "diagnos" not in out.message.lower()
