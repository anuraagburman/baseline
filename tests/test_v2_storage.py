"""Tests for v2 storage: extended profile + meals, targets, workouts, onboarding, oauth."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from baseline.domain.models import (
    Goal,
    MacroBreakdown,
    Meal,
    NutritionTargets,
    OnboardingState,
    Sex,
    UserProfile,
    WorkoutLog,
)
from baseline.storage import repository as repo
from baseline.storage.db import Database


@pytest.fixture
def db(tmp_path):
    database = Database(f"sqlite:///{tmp_path}/test.db")
    database.create_all()
    return database


def _full_profile():
    return UserProfile(
        user_id="u1", name="Pranav", age=36, sex=Sex.MALE, weight_kg=78.0,
        goal=Goal.LOSE_FAT, height_cm=178.0,
        body_measurements={"waist_cm": 86.0},
        workouts_per_week=4, workout_types=["strength", "running"],
        health_conditions=["hypertension"],
    )


def test_user_v2_fields_roundtrip(db):
    with db.session() as s:
        repo.upsert_user(s, _full_profile())
    with db.session() as s:
        got = repo.get_user(s, "u1")
    assert got.height_cm == 178.0
    assert got.body_measurements == {"waist_cm": 86.0}
    assert got.workouts_per_week == 4
    assert got.workout_types == ["strength", "running"]
    assert got.health_conditions == ["hypertension"]


def test_meal_save_and_fetch_for_day(db):
    with db.session() as s:
        repo.upsert_user(s, _full_profile())
        repo.save_meal(s, Meal(
            id="m1", user_id="u1", timestamp=datetime(2026, 6, 13, 8, 0),
            description="eggs", source="text",
            macros=MacroBreakdown(kcal=300, protein_g=20, carbs_g=2, fat_g=22),
        ))
        repo.save_meal(s, Meal(
            id="m2", user_id="u1", timestamp=datetime(2026, 6, 13, 13, 0),
            description="chicken rice", source="photo",
            macros=MacroBreakdown(kcal=520, protein_g=45, carbs_g=50, fat_g=12),
        ))
        repo.save_meal(s, Meal(
            id="m3", user_id="u1", timestamp=datetime(2026, 6, 14, 8, 0),
            description="next day", source="text",
            macros=MacroBreakdown(kcal=100, protein_g=5, carbs_g=10, fat_g=4),
        ))
    with db.session() as s:
        meals = repo.get_meals_for_day(s, "u1", date(2026, 6, 13))
    assert len(meals) == 2
    assert {m.id for m in meals} == {"m1", "m2"}


def test_nutrition_targets_set_and_get(db):
    with db.session() as s:
        repo.upsert_user(s, _full_profile())
        repo.set_nutrition_targets(s, "u1",
            NutritionTargets(kcal=2000, protein_g=150, carbs_g=200, fat_g=60))
    with db.session() as s:
        targets = repo.get_nutrition_targets(s, "u1")
    assert targets.protein_g == 150


def test_set_nutrition_targets_is_idempotent(db):
    with db.session() as s:
        repo.upsert_user(s, _full_profile())
        repo.set_nutrition_targets(s, "u1",
            NutritionTargets(kcal=2000, protein_g=150, carbs_g=200, fat_g=60))
        repo.set_nutrition_targets(s, "u1",
            NutritionTargets(kcal=1800, protein_g=160, carbs_g=180, fat_g=55))
    with db.session() as s:
        targets = repo.get_nutrition_targets(s, "u1")
    assert targets.kcal == 1800
    assert targets.protein_g == 160


def test_workout_log_and_week_fetch(db):
    with db.session() as s:
        repo.upsert_user(s, _full_profile())
        repo.log_workout(s, WorkoutLog(user_id="u1", date=date(2026, 6, 13),
                                       type="running", duration_min=30))
        repo.log_workout(s, WorkoutLog(user_id="u1", date=date(2026, 6, 11),
                                       type="strength", duration_min=45))
        # 10 days ago — outside the week window
        repo.log_workout(s, WorkoutLog(user_id="u1", date=date(2026, 6, 3),
                                       type="cycling", duration_min=60))
    with db.session() as s:
        week = repo.get_workouts_for_week(s, "u1", date(2026, 6, 13))
    assert len(week) == 2


def test_onboarding_state_save_and_resume(db):
    with db.session() as s:
        repo.save_onboarding_state(s, OnboardingState(
            user_id="u1", step="age", data={"name": "Pranav"}))
    with db.session() as s:
        st = repo.get_onboarding_state(s, "u1")
    assert st.step == "age"
    assert st.data["name"] == "Pranav"

    # advancing overwrites in place
    with db.session() as s:
        repo.save_onboarding_state(s, OnboardingState(
            user_id="u1", step="weight", data={"name": "Pranav", "age": 36}))
    with db.session() as s:
        st = repo.get_onboarding_state(s, "u1")
    assert st.step == "weight"
    assert st.data["age"] == 36


def test_onboarding_state_unknown_user_returns_none(db):
    with db.session() as s:
        assert repo.get_onboarding_state(s, "nobody") is None


def test_oauth_tokens_save_and_get(db):
    with db.session() as s:
        repo.upsert_user(s, _full_profile())
        repo.save_oauth_tokens(s, "u1", "google",
                               {"access_token": "abc", "refresh_token": "xyz"})
    with db.session() as s:
        tokens = repo.get_oauth_tokens(s, "u1", "google")
    assert tokens["access_token"] == "abc"
