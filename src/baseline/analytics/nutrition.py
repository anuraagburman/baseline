"""Nutrition engine — derive daily macro targets and track the daily ledger.

Targets are derived from the user's profile using the Mifflin–St Jeor equation
for resting metabolic rate, scaled by a training-activity factor, then adjusted
for the user's goal and split into protein / fat / carbohydrate. These are
sensible defaults the user can override conversationally — not prescriptions.
"""

from __future__ import annotations

from baseline.domain.models import (
    DailyNutritionLedger,
    Goal,
    MacroBreakdown,
    Meal,
    NutritionTargets,
    Sex,
    UserProfile,
)

_DEFAULT_HEIGHT_CM = 170.0  # fallback when the user hasn't given height yet

# Workouts/week → physical-activity factor (TDEE = BMR * factor).
def _activity_factor(workouts_per_week: int) -> float:
    if workouts_per_week <= 0:
        return 1.2
    if workouts_per_week <= 2:
        return 1.375
    if workouts_per_week <= 4:
        return 1.55
    if workouts_per_week <= 6:
        return 1.725
    return 1.9


# Goal → (kcal multiplier, protein g per kg bodyweight).
_GOAL_ADJUST = {
    Goal.LOSE_FAT: (0.80, 1.8),
    Goal.MORE_ENERGY: (1.0, 1.6),
    Goal.SLEEP_BETTER: (1.0, 1.4),
    Goal.GENERAL_HEALTH: (1.0, 1.4),
}


def _bmr(profile: UserProfile) -> float:
    """Mifflin–St Jeor resting metabolic rate (kcal/day)."""
    height = profile.height_cm if profile.height_cm is not None else _DEFAULT_HEIGHT_CM
    base = 10 * profile.weight_kg + 6.25 * height - 5 * profile.age
    if profile.sex is Sex.MALE:
        return base + 5
    if profile.sex is Sex.FEMALE:
        return base - 161
    return base - 78  # "other": midpoint of the male/female constants


def derive_targets(profile: UserProfile) -> NutritionTargets:
    """Compute daily macro targets from the profile."""
    tdee = _bmr(profile) * _activity_factor(profile.workouts_per_week)
    kcal_mult, protein_per_kg = _GOAL_ADJUST.get(profile.goal, (1.0, 1.4))
    kcal = tdee * kcal_mult

    protein_g = protein_per_kg * profile.weight_kg
    fat_g = (0.25 * kcal) / 9  # fat at 25% of calories
    carbs_g = (kcal - protein_g * 4 - fat_g * 9) / 4  # remainder as carbs

    return NutritionTargets(
        kcal=round(kcal),
        protein_g=round(protein_g),
        carbs_g=round(max(0.0, carbs_g)),
        fat_g=round(fat_g),
    )


def compute_ledger(
    targets: NutritionTargets, meals_today: list[Meal]
) -> DailyNutritionLedger:
    """Sum today's meals and return the ledger (targets, consumed, remaining)."""
    consumed = MacroBreakdown.zero()
    for meal in meals_today:
        consumed = consumed + meal.macros
    return DailyNutritionLedger(targets=targets, consumed=consumed)
