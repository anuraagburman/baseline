"""Tests for the conversational onboarding state machine (pure Q&A collection)."""

from __future__ import annotations

from baseline.domain.models import OnboardingState
from baseline.onboarding.conversation import OnboardingFSM


def _run(answers: list[str]):
    """Drive the FSM through a list of answers; return (final_reply, replies)."""
    fsm = OnboardingFSM()
    first = fsm.start("u1")
    replies = [first.reply]
    result = first
    for ans in answers:
        result = fsm.handle(result.state, ans)
        replies.append(result.reply)
    return result, replies


_HAPPY = [
    "Pranav",            # name
    "36",                # age
    "male",              # gender
    "78 kg",             # weight
    "178 cm",            # height
    "skip",              # measurements (optional)
    "4",                 # workouts/week
    "strength, running", # workout types
    "none",              # health conditions
    "I want to lose fat",# goal
    "connected",         # connect device
]


def test_start_greets_and_asks_for_name():
    fsm = OnboardingFSM()
    r = fsm.start("u1")
    assert r.state.step == "name"
    assert "name" in r.reply.lower()
    assert r.complete is False


def test_happy_path_completes_with_assembled_profile():
    result, _ = _run(_HAPPY)
    assert result.complete is True
    data = result.assembled
    assert data["name"] == "Pranav"
    assert data["age"] == 36
    assert data["sex"] == "male"
    assert data["weight_kg"] == 78.0
    assert data["height_cm"] == 178.0
    assert data["workouts_per_week"] == 4
    assert "strength" in data["workout_types"]
    assert data["health_conditions"] == []
    assert data["goal"] == "lose_fat"


def test_invalid_age_reasks_without_advancing():
    fsm = OnboardingFSM()
    r = fsm.start("u1")
    r = fsm.handle(r.state, "Pranav")   # name -> age
    assert r.state.step == "age"
    bad = fsm.handle(r.state, "not a number")
    assert bad.state.step == "age"      # did not advance
    assert "age" in bad.reply.lower()


def test_gender_shorthand_is_parsed():
    fsm = OnboardingFSM()
    r = fsm.start("u1")
    r = fsm.handle(r.state, "Sam")      # name
    r = fsm.handle(r.state, "40")       # age
    r = fsm.handle(r.state, "f")        # gender shorthand
    assert r.state.data["sex"] == "female"


def test_optional_measurements_can_be_skipped():
    result, _ = _run(_HAPPY)
    assert result.assembled["body_measurements"] is None


def test_measurements_can_be_provided():
    answers = list(_HAPPY)
    answers[5] = "waist 86, hip 98"   # measurements step
    result, _ = _run(answers)
    assert result.assembled["body_measurements"]["waist_cm"] == 86


def test_goal_freetext_maps_to_enum():
    answers = list(_HAPPY)
    answers[9] = "mostly I just want more energy"
    result, _ = _run(answers)
    assert result.assembled["goal"] == "more_energy"


def test_weight_with_units_parsed_to_float():
    result, _ = _run(_HAPPY)
    assert isinstance(result.assembled["weight_kg"], float)


def test_health_conditions_listed_when_present():
    answers = list(_HAPPY)
    answers[8] = "hypertension and asthma"
    result, _ = _run(answers)
    assert "hypertension" in result.assembled["health_conditions"]
    assert "asthma" in result.assembled["health_conditions"]


def test_welcome_mentions_capabilities():
    r = OnboardingFSM().start("u1")
    low = r.reply.lower()
    # gives the user a sense of what the chat can do (low cognitive load framing)
    assert any(w in low for w in ["food", "meal", "photo", "daily", "workout", "track"])
