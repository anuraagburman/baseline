"""Conversational onboarding — a friendly, one-question-at-a-time state machine.

The FSM is pure: given the current :class:`OnboardingState` and the user's
message, it parses the answer, advances (or gently re-asks on a bad answer), and
returns the next prompt. When the last step is done it returns ``complete=True``
with an assembled profile dict. Persistence (between WhatsApp messages) and the
finalize step (device connect + backfill + first insight) are wired by the
caller, reusing :func:`baseline.onboarding.flow.onboard_user`.

Design goal: minimal cognitive load — short questions, tolerant parsing, optional
steps skippable, and the occasional reminder of what the chat can do.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from baseline.domain.models import Goal, OnboardingState


class ParseError(ValueError):
    """Raised by a step parser when the answer can't be understood."""


@dataclass
class Step:
    key: str
    prompt: str
    parse: Callable[[str], Any]
    optional: bool = False


@dataclass
class FSMReply:
    reply: str
    state: OnboardingState
    complete: bool = False
    assembled: dict | None = None


_SKIP_TOKENS = {"skip", "none", "no", "n/a", "na", "-"}


# --- parsers (each returns a value or raises ParseError) ---

def _parse_name(text: str) -> str:
    name = text.strip()
    if not name:
        raise ParseError("I didn't catch your name — what should I call you?")
    return name


def _parse_age(text: str) -> int:
    import re

    m = re.search(r"\b(\d{1,3})\b", text)
    if not m:
        raise ParseError("Just a number works for your age — how old are you?")
    age = int(m.group(1))
    if not 10 <= age <= 100:
        raise ParseError("That age doesn't look right — what's your age in years?")
    return age


def _parse_gender(text: str) -> str:
    t = text.strip().lower()
    if t in {"m", "male", "man", "boy"}:
        return "male"
    if t in {"f", "female", "woman", "girl"}:
        return "female"
    if t in {"o", "other", "nonbinary", "non-binary", "nb"}:
        return "other"
    raise ParseError("No problem — just reply male, female, or other.")


def _parse_weight(text: str) -> float:
    import re

    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if not m:
        raise ParseError("How much do you weigh? You can say e.g. '78 kg'.")
    kg = float(m.group(1))
    if "lb" in text.lower() or "pound" in text.lower():
        kg = kg * 0.4536
    if not 30 <= kg <= 400:
        raise ParseError("That weight looks off — what's your weight in kg?")
    return round(kg, 1)


def _parse_height(text: str) -> float:
    import re

    # feet/inches, e.g. 5'10 or 5 ft 10
    ft = re.search(r"(\d)\s*(?:'|ft|feet)\s*(\d{1,2})?", text.lower())
    if ft:
        feet = int(ft.group(1))
        inches = int(ft.group(2)) if ft.group(2) else 0
        cm = (feet * 12 + inches) * 2.54
        if 100 <= cm <= 250:
            return round(cm, 1)
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if not m:
        raise ParseError("How tall are you? You can say e.g. '178 cm' or 5'10\".")
    cm = float(m.group(1))
    if not 100 <= cm <= 250:
        raise ParseError("That height looks off — what's your height in cm?")
    return round(cm, 1)


def _parse_measurements(text: str) -> dict | None:
    import re

    if text.strip().lower() in _SKIP_TOKENS:
        return None
    out: dict[str, float] = {}
    for part in ("waist", "hip", "chest"):
        m = re.search(rf"{part}\D*(\d+(?:\.\d+)?)", text.lower())
        if m:
            out[f"{part}_cm"] = float(m.group(1))
    # Optional step: if nothing parsed, treat as skip rather than error.
    return out or None


def _parse_workouts_per_week(text: str) -> int:
    import re

    if text.strip().lower() in _SKIP_TOKENS:
        return 0
    m = re.search(r"\b(\d{1,2})\b", text)
    if not m:
        raise ParseError("Roughly how many times a week do you work out? A number is fine.")
    n = int(m.group(1))
    if not 0 <= n <= 21:
        raise ParseError("How many workouts in a typical week?")
    return n


def _parse_workout_types(text: str) -> list[str]:
    import re

    if text.strip().lower() in _SKIP_TOKENS:
        return []
    parts = re.split(r",|/|\band\b|\+|&", text.lower())
    return [p.strip() for p in parts if p.strip()]


def _parse_conditions(text: str) -> list[str]:
    import re

    if text.strip().lower() in _SKIP_TOKENS:
        return []
    parts = re.split(r",|/|\band\b|\+|&", text.lower())
    return [p.strip() for p in parts if p.strip()]


def _parse_goal(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["fat", "weight", "lose", "lean", "slim"]):
        return Goal.LOSE_FAT.value
    if "sleep" in t:
        return Goal.SLEEP_BETTER.value
    if any(w in t for w in ["energy", "fatigue", "tired", "stamina"]):
        return Goal.MORE_ENERGY.value
    if any(w in t for w in ["health", "general", "fit", "overall", "longevity"]):
        return Goal.GENERAL_HEALTH.value
    raise ParseError(
        "Pick what fits best: lose fat, sleep better, more energy, or general health."
    )


def _parse_connect(text: str) -> str:
    # Any reply moves on; real OAuth is wired separately (Loop 9).
    return text.strip().lower()


_STEPS: list[Step] = [
    Step("name", "First up — what's your name?", _parse_name),
    Step("age", "Nice to meet you! How old are you?", _parse_age),
    Step("sex", "Got it. And your gender — male, female, or other?", _parse_gender),
    Step("weight_kg", "What's your weight? (e.g. '78 kg')", _parse_weight),
    Step("height_cm", "And your height? (e.g. '178 cm' or 5'10\")", _parse_height),
    Step("body_measurements",
         "Optional: any body measurements like waist/hip? Reply 'skip' to skip.",
         _parse_measurements, optional=True),
    Step("workouts_per_week",
         "How many times a week do you usually work out?", _parse_workouts_per_week),
    Step("workout_types",
         "What kind of workouts? (e.g. strength, running, yoga)", _parse_workout_types),
    Step("health_conditions",
         "Any health conditions I should keep in mind? Reply 'none' if not.",
         _parse_conditions),
    Step("goal",
         "Last thing — what's your main goal right now? "
         "Lose fat, sleep better, more energy, or general health?", _parse_goal),
    Step("connect",
         "Perfect 🙌 Connect your Google Health device so I can read your steps, "
         "sleep and heart rate (read-only). Reply 'connect' when you're ready.",
         _parse_connect),
]

_WELCOME = (
    "Hi! I'm Baseline 👋 your personal health coach, right here in chat.\n\n"
    "I turn your wearable data into one simple daily tip, I can log your meals "
    "from a photo and track your macros, and I keep an eye on your workouts and "
    "steps — all without any apps or forms.\n\n"
    "Let's get you set up in under two minutes. {first}"
)


class OnboardingFSM:
    """Drives the conversational onboarding. Pure: no DB, no network."""

    def __init__(self, steps: list[Step] | None = None) -> None:
        self._steps = steps or _STEPS
        self._index = {s.key: i for i, s in enumerate(self._steps)}

    def start(self, user_id: str) -> FSMReply:
        first = self._steps[0]
        state = OnboardingState(user_id=user_id, step=first.key, data={})
        return FSMReply(reply=_WELCOME.format(first=first.prompt), state=state)

    def handle(self, state: OnboardingState, message: str) -> FSMReply:
        step = self._steps[self._index[state.step]]
        try:
            value = step.parse(message)
        except ParseError as e:
            # Re-ask the same step with the gentle clarification.
            return FSMReply(reply=str(e), state=state)

        data = dict(state.data)
        data[step.key] = value

        next_i = self._index[state.step] + 1
        if next_i >= len(self._steps):
            assembled = self._assemble(data)
            done_state = OnboardingState(
                user_id=state.user_id, step=state.step, data=data, complete=True
            )
            closing = (
                "All set! Give me a moment to analyse your recent data and I'll "
                "send your first insight. 📈"
            )
            return FSMReply(reply=closing, state=done_state, complete=True, assembled=assembled)

        next_step = self._steps[next_i]
        new_state = OnboardingState(
            user_id=state.user_id, step=next_step.key, data=data
        )
        ack = _ack_for(step.key, value)
        reply = f"{ack}{next_step.prompt}" if ack else next_step.prompt
        return FSMReply(reply=reply, state=new_state)

    @staticmethod
    def _assemble(data: dict) -> dict:
        """Normalise collected answers into the profile-shaped dict."""
        return {
            "name": data.get("name"),
            "age": data.get("age"),
            "sex": data.get("sex"),
            "weight_kg": data.get("weight_kg"),
            "height_cm": data.get("height_cm"),
            "body_measurements": data.get("body_measurements"),
            "workouts_per_week": data.get("workouts_per_week", 0),
            "workout_types": data.get("workout_types", []),
            "health_conditions": data.get("health_conditions", []),
            "goal": data.get("goal"),
        }


def _ack_for(step_key: str, value: Any) -> str:
    """A short, warm acknowledgement before the next question."""
    if step_key == "name":
        return ""  # the next prompt already greets by reusing 'Nice to meet you'
    if step_key == "goal":
        return "Love it. "
    return ""
