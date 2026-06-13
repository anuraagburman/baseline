"""Food → macros estimation behind a narrow interface.

v1 ships:
- :class:`MockNutritionEstimator` — deterministic, offline. Parses a text
  description against a small food table (and falls back to a generic estimate),
  so the whole logging flow runs and is testable with no API key.
- :class:`ClaudeNutritionEstimator` — Claude vision estimates macros from a food
  photo (and/or caption), returning structured JSON.

Both implement :class:`NutritionEstimator`. The estimate is explicitly an
estimate — every Meal carries a confidence — and is never framed as medical
nutrition advice.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Protocol, runtime_checkable

from baseline.domain.models import MacroBreakdown, Meal
from baseline.util import utcnow


@runtime_checkable
class NutritionEstimator(Protocol):
    def from_text(self, user_id: str, text: str) -> Meal:
        """Estimate a meal's macros from a text description."""
        ...

    def from_image(self, user_id: str, image_bytes: bytes, caption: str | None = None) -> Meal:
        """Estimate a meal's macros from a food photo (and optional caption)."""
        ...


# Per-100g macros for common foods: (kcal, protein_g, carbs_g, fat_g).
_FOOD_DB: dict[str, tuple[float, float, float, float]] = {
    "chicken": (165, 31, 0, 3.6),
    "beef": (250, 26, 0, 15),
    "fish": (206, 22, 0, 12),
    "salmon": (208, 20, 0, 13),
    "egg": (155, 13, 1.1, 11),
    "rice": (130, 2.7, 28, 0.3),
    "pasta": (157, 5.8, 31, 0.9),
    "bread": (265, 9, 49, 3.2),
    "roti": (264, 9, 46, 4),
    "potato": (87, 1.9, 20, 0.1),
    "dal": (116, 9, 20, 0.4),
    "lentil": (116, 9, 20, 0.4),
    "paneer": (265, 18, 1.2, 21),
    "tofu": (76, 8, 1.9, 4.8),
    "salad": (50, 2, 6, 2),
    "oats": (389, 17, 66, 7),
    "banana": (89, 1.1, 23, 0.3),
    "apple": (52, 0.3, 14, 0.2),
    "milk": (60, 3.2, 5, 3.3),
    "yogurt": (59, 10, 3.6, 0.4),
    "cheese": (402, 25, 1.3, 33),
    "avocado": (160, 2, 9, 15),
    "nuts": (607, 21, 20, 54),
}

_DEFAULT_SERVING_G = 150.0
_GENERIC_MEAL = MacroBreakdown(kcal=450, protein_g=20, carbs_g=45, fat_g=18)


def _macros_for_food(food: str, grams: float) -> MacroBreakdown:
    kcal, p, c, f = _FOOD_DB[food]
    scale = grams / 100.0
    return MacroBreakdown(
        kcal=round(kcal * scale, 1),
        protein_g=round(p * scale, 1),
        carbs_g=round(c * scale, 1),
        fat_g=round(f * scale, 1),
    )


def _parse_text(text: str) -> tuple[MacroBreakdown, float]:
    """Return (macros, confidence) for a free-text food description."""
    lowered = text.lower()
    grams_match = re.search(r"(\d+)\s*g\b", lowered)
    grams = float(grams_match.group(1)) if grams_match else _DEFAULT_SERVING_G

    matched = [food for food in _FOOD_DB if food in lowered]
    if not matched:
        return _GENERIC_MEAL, 0.3

    total = MacroBreakdown.zero()
    for food in matched:
        total = total + _macros_for_food(food, grams)

    # Higher confidence when the user specified a quantity.
    confidence = 0.7 if grams_match else 0.5
    return total, confidence


class MockNutritionEstimator:
    def from_text(self, user_id: str, text: str) -> Meal:
        macros, confidence = _parse_text(text)
        return Meal(
            id=uuid.uuid4().hex,
            user_id=user_id,
            timestamp=utcnow(),
            description=text,
            source="text",
            macros=macros,
            confidence=confidence,
        )

    def from_image(self, user_id: str, image_bytes: bytes, caption: str | None = None) -> Meal:
        if caption:
            macros, confidence = _parse_text(caption)
            description = caption
        else:
            # Mock can't actually see the image — return a plausible default.
            macros, confidence = _GENERIC_MEAL, 0.4
            description = "a logged meal (photo)"
        return Meal(
            id=uuid.uuid4().hex,
            user_id=user_id,
            timestamp=utcnow(),
            description=description,
            source="photo",
            macros=macros,
            confidence=confidence,
        )


_VISION_PROMPT = (
    "You are a nutrition estimator. Look at the food and respond with ONLY a JSON "
    "object: {\"description\": str, \"kcal\": number, \"protein_g\": number, "
    "\"carbs_g\": number, \"fat_g\": number, \"confidence\": number between 0 and 1}. "
    "Estimate typical portion sizes. Do not give medical or dietary advice."
)


class ClaudeNutritionEstimator:
    """Real macro estimation via Claude vision."""

    def __init__(self, model: str = "claude-opus-4-8", api_key: str | None = None) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def _parse_response(self, user_id: str, text_response: str, description: str, source: str) -> Meal:
        data = json.loads(text_response)
        return Meal(
            id=uuid.uuid4().hex,
            user_id=user_id,
            timestamp=utcnow(),
            description=data.get("description", description),
            source=source,  # type: ignore[arg-type]
            macros=MacroBreakdown(
                kcal=data["kcal"], protein_g=data["protein_g"],
                carbs_g=data["carbs_g"], fat_g=data["fat_g"],
            ),
            confidence=float(data.get("confidence", 0.6)),
        )

    def from_text(self, user_id: str, text: str) -> Meal:
        resp = self._client.messages.create(
            model=self._model, max_tokens=300, system=_VISION_PROMPT,
            messages=[{"role": "user", "content": f"Food: {text}"}],
        )
        return self._parse_response(user_id, resp.content[0].text, text, "text")

    def from_image(self, user_id: str, image_bytes: bytes, caption: str | None = None) -> Meal:
        import base64

        content = [
            {"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg",
                "data": base64.b64encode(image_bytes).decode(),
            }},
            {"type": "text", "text": caption or "What food is this? Estimate the macros."},
        ]
        resp = self._client.messages.create(
            model=self._model, max_tokens=300, system=_VISION_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        return self._parse_response(user_id, resp.content[0].text, caption or "photo", "photo")


def build_nutrition_estimator(provider: str, model: str, api_key: str | None) -> NutritionEstimator:
    """Factory — mock unless a real vision provider is configured."""
    if provider == "claude":
        return ClaudeNutritionEstimator(model=model, api_key=api_key)
    return MockNutritionEstimator()
