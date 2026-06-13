"""Tests for the nutrition engine: target derivation and the daily ledger.

Mifflin-St Jeor (male): BMR = 10*kg + 6.25*cm - 5*age + 5
Worked example used below: male, 78kg, 178cm, age 36, 4 workouts/wk, lose_fat
  BMR  = 780 + 1112.5 - 180 + 5 = 1717.5
  TDEE = 1717.5 * 1.55 (3-4 wk) = 2662.125
  cut  = *0.8 = 2129.7 kcal
  protein = 1.8 g/kg * 78 = 140.4 g
"""

from __future__ import annotations

from datetime import datetime

import pytest

from baseline.analytics.nutrition import compute_ledger, derive_targets
from baseline.domain.models import (
    Goal,
    MacroBreakdown,
    Meal,
    NutritionTargets,
    Sex,
    UserProfile,
)


def _profile(goal=Goal.LOSE_FAT, workouts=4, **kw):
    base = dict(user_id="u1", age=36, sex=Sex.MALE, weight_kg=78.0,
                goal=goal, height_cm=178.0, workouts_per_week=workouts)
    base.update(kw)
    return UserProfile(**base)


def test_derive_targets_matches_mifflin_st_jeor_worked_example():
    t = derive_targets(_profile())
    assert t.kcal == pytest.approx(2130, abs=5)
    assert t.protein_g == pytest.approx(140, abs=1)
    # fat ≈ 25% kcal / 9; carbs = remainder / 4
    assert t.fat_g == pytest.approx(59, abs=2)
    assert t.carbs_g == pytest.approx(259, abs=3)


def test_maintenance_goal_has_more_kcal_than_fat_loss():
    cut = derive_targets(_profile(goal=Goal.LOSE_FAT))
    maintain = derive_targets(_profile(goal=Goal.GENERAL_HEALTH))
    assert maintain.kcal > cut.kcal


def test_protein_is_higher_for_fat_loss():
    cut = derive_targets(_profile(goal=Goal.LOSE_FAT))
    maintain = derive_targets(_profile(goal=Goal.GENERAL_HEALTH))
    assert cut.protein_g > maintain.protein_g


def test_more_workouts_raises_kcal_target():
    sedentary = derive_targets(_profile(workouts=0))
    active = derive_targets(_profile(workouts=6))
    assert active.kcal > sedentary.kcal


def test_missing_height_does_not_crash_and_returns_positive_targets():
    p = _profile()
    p.height_cm = None
    t = derive_targets(p)
    assert t.kcal > 0 and t.protein_g > 0


def test_female_has_lower_bmr_than_male_same_stats():
    male = derive_targets(_profile(sex=Sex.MALE))
    female = derive_targets(_profile(sex=Sex.FEMALE))
    assert female.kcal < male.kcal


# --- Ledger ---

def _meal(protein, carbs, fat, kcal):
    return Meal(id="m", user_id="u1", timestamp=datetime(2026, 6, 13, 12),
                description="x", source="text",
                macros=MacroBreakdown(kcal=kcal, protein_g=protein, carbs_g=carbs, fat_g=fat))


def test_ledger_with_no_meals_leaves_full_targets_remaining():
    targets = NutritionTargets(kcal=2000, protein_g=150, carbs_g=200, fat_g=60)
    ledger = compute_ledger(targets, [])
    assert ledger.remaining().protein_g == 150
    assert ledger.consumed.kcal == 0


def test_ledger_sums_meals_and_computes_remaining():
    targets = NutritionTargets(kcal=2000, protein_g=150, carbs_g=200, fat_g=60)
    meals = [_meal(40, 30, 12, 400), _meal(50, 60, 15, 600)]
    ledger = compute_ledger(targets, meals)
    assert ledger.consumed.protein_g == 90
    assert ledger.remaining().protein_g == 60
    assert ledger.remaining().kcal == 1000


def test_ledger_remaining_negative_when_over_target():
    targets = NutritionTargets(kcal=1000, protein_g=80, carbs_g=100, fat_g=30)
    meals = [_meal(100, 120, 40, 1200)]
    assert compute_ledger(targets, meals).remaining().kcal == -200
