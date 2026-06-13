"""Tests for v2 domain models: extended profile, nutrition, workouts, onboarding."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from baseline.domain.models import (
    ActivitySummary,
    DailyNutritionLedger,
    Goal,
    MacroBreakdown,
    Meal,
    NutritionTargets,
    OnboardingState,
    Sex,
    UserProfile,
    WorkoutLog,
)


def test_user_profile_has_new_v2_fields_with_defaults():
    p = UserProfile(
        user_id="u1", age=30, sex=Sex.MALE, weight_kg=78.0, goal=Goal.LOSE_FAT
    )
    assert p.height_cm is None
    assert p.body_measurements is None
    assert p.workouts_per_week == 0
    assert p.workout_types == []
    assert p.health_conditions == []


def test_user_profile_accepts_full_v2_payload():
    p = UserProfile(
        user_id="u1", name="Pranav", age=36, sex=Sex.MALE, weight_kg=78.0,
        goal=Goal.LOSE_FAT, height_cm=178.0,
        body_measurements={"waist_cm": 86, "hip_cm": 98},
        workouts_per_week=4, workout_types=["strength", "running"],
        health_conditions=["hypertension"],
    )
    assert p.height_cm == 178.0
    assert p.workouts_per_week == 4
    assert "strength" in p.workout_types
    assert "hypertension" in p.health_conditions


def test_macro_breakdown_sums_with_plus_operator():
    a = MacroBreakdown(kcal=400, protein_g=40, carbs_g=30, fat_g=12)
    b = MacroBreakdown(kcal=250, protein_g=20, carbs_g=35, fat_g=8)
    total = a + b
    assert total.kcal == 650
    assert total.protein_g == 60
    assert total.carbs_g == 65
    assert total.fat_g == 20


def test_meal_constructs_with_macros_and_source():
    m = Meal(
        id="m1", user_id="u1", timestamp=datetime(2026, 6, 13, 12, 30),
        description="grilled chicken and rice",
        source="photo",
        macros=MacroBreakdown(kcal=520, protein_g=45, carbs_g=50, fat_g=12),
        confidence=0.7,
    )
    assert m.source == "photo"
    assert m.macros.protein_g == 45


def test_meal_rejects_invalid_source():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Meal(id="m1", user_id="u1", timestamp=datetime.now(),
             description="x", source="telepathy",
             macros=MacroBreakdown(kcal=0, protein_g=0, carbs_g=0, fat_g=0),
             confidence=1.0)


def test_nutrition_ledger_computes_remaining():
    targets = NutritionTargets(kcal=2000, protein_g=150, carbs_g=200, fat_g=60)
    consumed = MacroBreakdown(kcal=1200, protein_g=90, carbs_g=120, fat_g=35)
    ledger = DailyNutritionLedger(targets=targets, consumed=consumed)
    remaining = ledger.remaining()
    assert remaining.protein_g == 60
    assert remaining.kcal == 800
    assert remaining.carbs_g == 80
    assert remaining.fat_g == 25


def test_nutrition_ledger_remaining_can_go_negative_when_over():
    targets = NutritionTargets(kcal=2000, protein_g=150, carbs_g=200, fat_g=60)
    consumed = MacroBreakdown(kcal=2200, protein_g=160, carbs_g=210, fat_g=70)
    remaining = DailyNutritionLedger(targets=targets, consumed=consumed).remaining()
    assert remaining.protein_g == -10
    assert remaining.kcal == -200


def test_workout_log_constructs():
    w = WorkoutLog(user_id="u1", date=date(2026, 6, 13), type="running",
                   duration_min=35, source="manual")
    assert w.type == "running"
    assert w.duration_min == 35


def test_activity_summary_constructs():
    s = ActivitySummary(
        days_worked_out_this_week=3, current_streak=2,
        steps_today=9100, steps_7d_avg=8200.0, active_minutes=42,
    )
    assert s.current_streak == 2
    assert s.steps_today == 9100


def test_onboarding_state_tracks_step_and_partial_data():
    st = OnboardingState(user_id="u1", step="age", data={"name": "Pranav"})
    assert st.step == "age"
    assert st.data["name"] == "Pranav"
    assert st.complete is False
