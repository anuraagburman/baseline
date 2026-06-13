"""Tests for the coach's nutrition and activity replies (deterministic, faithful)."""

from __future__ import annotations

import re
from datetime import date, datetime

from baseline.coach.coach import Coach
from baseline.coach.llm import MockLLM
from baseline.coach.retriever import SimpleEvidenceRetriever
from baseline.domain.models import (
    ActivitySummary,
    DailyNutritionLedger,
    Goal,
    MacroBreakdown,
    Meal,
    NutritionTargets,
    Sex,
    UserProfile,
)


def _coach():
    return Coach(llm=MockLLM(), retriever=SimpleEvidenceRetriever())


def _profile():
    return UserProfile(user_id="u1", name="Pranav", age=36, sex=Sex.MALE,
                       weight_kg=78.0, goal=Goal.LOSE_FAT)


def _meal(protein=45, carbs=50, fat=12, kcal=520, desc="grilled chicken and rice"):
    return Meal(id="m1", user_id="u1", timestamp=datetime(2026, 6, 13, 13),
                description=desc, source="photo",
                macros=MacroBreakdown(kcal=kcal, protein_g=protein, carbs_g=carbs, fat_g=fat),
                confidence=0.7)


def _ledger(consumed_protein=45, consumed_kcal=520):
    return DailyNutritionLedger(
        targets=NutritionTargets(kcal=2130, protein_g=140, carbs_g=259, fat_g=59),
        consumed=MacroBreakdown(kcal=consumed_kcal, protein_g=consumed_protein, carbs_g=50, fat_g=12),
    )


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+", text))


def test_nutrition_reply_logs_meal_and_shows_remaining_protein():
    reply = _coach().nutrition_reply(_profile(), _meal(), _ledger())
    assert "chicken" in reply.lower()
    assert "45" in reply         # logged protein
    assert "95" in reply         # remaining protein 140-45


def test_nutrition_reply_is_faithful_no_invented_numbers():
    meal = _meal(protein=45, carbs=50, fat=12, kcal=520)
    ledger = _ledger(consumed_protein=45, consumed_kcal=520)
    reply = _coach().nutrition_reply(_profile(), meal, ledger)
    remaining = ledger.remaining()
    allowed = {
        "45", "50", "12", "520",                                   # meal macros
        "140", "259", "59", "2130",                                # targets
        str(int(remaining.protein_g)), str(int(remaining.kcal)),   # remaining
        str(int(remaining.carbs_g)), str(int(remaining.fat_g)),
    }
    invented = _numbers(reply) - allowed
    assert not invented, f"invented numbers: {invented}"


def test_nutrition_reply_celebrates_when_protein_goal_hit():
    ledger = DailyNutritionLedger(
        targets=NutritionTargets(kcal=2000, protein_g=140, carbs_g=200, fat_g=60),
        consumed=MacroBreakdown(kcal=1800, protein_g=150, carbs_g=180, fat_g=55),
    )
    reply = _coach().nutrition_reply(_profile(), _meal(), ledger)
    assert "goal" in reply.lower() or "hit" in reply.lower() or "🎯" in reply


def test_nutrition_reply_has_no_medical_or_diagnostic_language():
    reply = _coach().nutrition_reply(_profile(), _meal(), _ledger())
    low = reply.lower()
    assert "diagnos" not in low
    assert "you have" not in low or "you have" in low and "left" in low  # 'you have X left' is fine


def test_activity_reply_mentions_streak_and_steps():
    summary = ActivitySummary(days_worked_out_this_week=3, current_streak=2,
                              steps_today=9100, steps_7d_avg=8200.0, active_minutes=42)
    reply = _coach().activity_reply(_profile(), summary)
    assert "2" in reply       # streak
    assert "9100" in reply or "9,100" in reply
    assert "3" in reply       # days this week


def test_activity_reply_encourages_when_no_streak():
    summary = ActivitySummary(days_worked_out_this_week=0, current_streak=0,
                              steps_today=2000, steps_7d_avg=3000.0, active_minutes=5)
    reply = _coach().activity_reply(_profile(), summary)
    assert reply
    assert "🔥" not in reply  # don't celebrate a zero streak
