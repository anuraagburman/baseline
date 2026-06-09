"""Tests for the coach system prompt and structured context rendering."""

from __future__ import annotations

from baseline.coach.prompt import (
    SYSTEM_PROMPT,
    CoachContext,
    frame_deviation,
    render_user_prompt,
)
from baseline.domain.models import (
    Deviation,
    EvidenceSnippet,
    Goal,
    Sex,
    TriageRoute,
    UserProfile,
)


def _profile():
    return UserProfile(
        user_id="u1", name="Pranav", age=36, sex=Sex.MALE, weight_kg=78.0, goal=Goal.LOSE_FAT
    )


def _context(**overrides):
    base = dict(
        profile=_profile(),
        route=TriageRoute.COACH,
        deviations=[
            Deviation(
                metric="rhr", value=64.0, median=58.0, z=2.3,
                direction="above", sustained=True, confidence="high",
            )
        ],
        today_summary="8,400 steps, slept 7h00m, resting HR 64 bpm.",
        evidence=[
            EvidenceSnippet(id="rhr-load", topic="rhr recovery",
                            text="Elevated resting HR often reflects incomplete recovery.",
                            citation="Buchheit 2014.")
        ],
        cold_start=False,
        user_message=None,
    )
    base.update(overrides)
    return CoachContext(**base)


def test_system_prompt_forbids_diagnosis_and_disclaims_medical_advice():
    lowered = SYSTEM_PROMPT.lower()
    assert "diagnos" in lowered  # e.g. "do not diagnose"
    assert "not medical advice" in lowered or "not a doctor" in lowered


def test_frame_deviation_uses_friendly_label_and_personal_framing():
    dev = Deviation(metric="rhr", value=64.0, median=58.0, z=2.3,
                    direction="above", sustained=True, confidence="high")
    framed = frame_deviation(dev)
    assert "resting heart rate" in framed
    assert "6" in framed and "above" in framed and "usual" in framed
    assert "rhr" not in framed  # raw metric name replaced


def test_render_includes_goal_today_summary_deviation_and_citation():
    text = render_user_prompt(_context())
    assert "lose_fat" in text or "fat" in text.lower()
    assert "8,400 steps" in text
    assert "resting heart rate is 6 above your usual 58" in text
    assert "Buchheit 2014." in text


def test_render_includes_user_question_on_followup_turn():
    text = render_user_prompt(_context(user_message="why is my heart rate up?"))
    assert "why is my heart rate up?" in text


def test_render_flags_cold_start_when_set():
    text = render_user_prompt(_context(cold_start=True))
    assert "learning" in text.lower() or "cold" in text.lower()
