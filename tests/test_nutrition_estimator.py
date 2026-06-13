"""Tests for the nutrition estimator (food -> macros)."""

from __future__ import annotations

import pytest

from baseline.domain.models import Meal
from baseline.nutrition.estimator import MockNutritionEstimator, NutritionEstimator


def test_mock_satisfies_protocol():
    assert isinstance(MockNutritionEstimator(), NutritionEstimator)


def test_from_text_with_grams_scales_macros():
    meal = MockNutritionEstimator().from_text("u1", "grilled chicken 200g")
    assert isinstance(meal, Meal)
    assert meal.source == "text"
    # chicken ~31g protein/100g -> ~62g for 200g
    assert meal.macros.protein_g == pytest.approx(62, abs=3)
    assert meal.macros.carbs_g == pytest.approx(0, abs=2)


def test_from_text_without_grams_uses_default_serving():
    meal = MockNutritionEstimator().from_text("u1", "chicken and rice")
    assert meal.macros.protein_g > 0
    assert meal.macros.carbs_g > 0  # rice contributes carbs


def test_from_text_combines_multiple_foods():
    one = MockNutritionEstimator().from_text("u1", "rice")
    two = MockNutritionEstimator().from_text("u1", "rice and chicken")
    assert two.macros.protein_g > one.macros.protein_g


def test_from_text_unknown_food_returns_low_confidence_estimate():
    meal = MockNutritionEstimator().from_text("u1", "moon rocks")
    assert meal.macros.kcal >= 0
    assert meal.confidence < 0.5


def test_from_text_is_deterministic():
    a = MockNutritionEstimator().from_text("u1", "chicken and rice")
    b = MockNutritionEstimator().from_text("u1", "chicken and rice")
    assert a.macros == b.macros


def test_from_image_returns_a_photo_meal_with_macros():
    meal = MockNutritionEstimator().from_image("u1", b"\xff\xd8\xff fake jpeg bytes")
    assert meal.source == "photo"
    assert meal.macros.kcal > 0


def test_from_image_with_caption_uses_caption_for_estimate():
    # caption naming a food should steer the estimate toward it
    meal = MockNutritionEstimator().from_image("u1", b"bytes", caption="chicken 200g")
    assert meal.macros.protein_g == pytest.approx(62, abs=3)
