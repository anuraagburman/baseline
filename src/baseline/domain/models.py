"""Provider-agnostic domain models — the vocabulary every layer speaks.

These types are the contract between the data sources, the analytics engine,
the coach, and the API. Nothing downstream references a vendor: a wearable's
data becomes a :class:`DailyMetrics`, and that is all the rest of the system
knows about.
"""

from __future__ import annotations

from datetime import date as Date
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from baseline.util import utcnow

Direction = Literal["above", "below", "normal"]
Confidence = Literal["high", "low"]


class Goal(str, Enum):
    """The user's self-chosen focus, which steers coaching emphasis."""

    LOSE_FAT = "lose_fat"
    SLEEP_BETTER = "sleep_better"
    MORE_ENERGY = "more_energy"
    GENERAL_HEALTH = "general_health"


class Sex(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class TriageRoute(str, Enum):
    """Where a triaged signal is routed."""

    MONITOR = "monitor"
    COACH = "coach"
    ESCALATE = "escalate"


class SleepStages(BaseModel):
    deep: int  # minutes
    rem: int
    light: int


class Nutrition(BaseModel):
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float


class Body(BaseModel):
    weight_kg: float
    body_fat_pct: float | None = None


class DailyMetrics(BaseModel):
    """One day of normalised wearable data — the source-abstraction shape.

    Every :class:`~baseline.sources.base.HealthSource` returns this, whatever
    the underlying device or API.
    """

    date: Date
    rhr: float  # resting heart rate, bpm
    hrv: float  # heart-rate variability, ms
    sleep_mins: int
    sleep_stages: SleepStages
    spo2: float  # blood oxygen, %
    resp_rate: float  # breaths/min
    vo2max: float | None = None
    steps: int
    active_zone_mins: int
    calories_out: float
    nutrition: Nutrition | None = None
    body: Body | None = None

    def summary(self) -> str:
        """A one-line, plain-language description of the day.

        Used as the human-readable day summary that feeds the coach context
        (and, later, day-summary embeddings for RAG). Deliberately neutral —
        no interpretation or medical framing.
        """
        hours = self.sleep_mins // 60
        minutes = self.sleep_mins % 60
        parts = [
            f"{self.steps:,} steps",
            f"slept {hours}h{minutes:02d}m",
            f"resting HR {self.rhr:.0f} bpm",
            f"HRV {self.hrv:.0f} ms",
            f"SpO2 {self.spo2:.0f}%",
        ]
        if self.nutrition is not None:
            parts.append(f"{self.nutrition.kcal:.0f} kcal in")
        return ", ".join(parts) + "."


class Deviation(BaseModel):
    """How far a single metric sits from the user's own normal."""

    metric: str
    value: float
    median: float
    z: float
    direction: Direction
    sustained: bool
    confidence: Confidence

    @property
    def abs_z(self) -> float:
        return abs(self.z)

    def describe(self) -> str:
        """Render the deviation in plain, self-referential language.

        e.g. ``"resting HR is 6 above your usual 58"``. This deviation framing
        ("X above your usual") is how the coach grounds claims in the user's
        own data rather than generic numbers.
        """
        delta = abs(self.value - self.median)
        delta_str = f"{delta:.0f}" if delta == round(delta) else f"{delta:.1f}"
        usual_str = (
            f"{self.median:.0f}"
            if self.median == round(self.median)
            else f"{self.median:.1f}"
        )
        if self.direction == "normal":
            return f"{self.metric} is around your usual {usual_str}"
        return (
            f"{self.metric} is {delta_str} {self.direction} your usual {usual_str}"
        )


class UserProfile(BaseModel):
    """Who the user is — drives goal emphasis, target derivation, and the
    pretest-probability gate.

    The v2 fields (height, measurements, training habits, conditions) feed the
    nutrition/activity engines and the safety logic; all are optional so a
    partially-onboarded user is still a valid profile.
    """

    user_id: str
    name: str | None = None
    age: int
    sex: Sex
    weight_kg: float
    goal: Goal
    history_flags: list[str] = Field(default_factory=list)
    delivery_pref: Literal["morning", "evening", "both"] = "evening"
    # --- v2 ---
    height_cm: float | None = None
    body_measurements: dict[str, float] | None = None  # waist_cm, hip_cm, chest_cm
    workouts_per_week: int = 0
    workout_types: list[str] = Field(default_factory=list)
    health_conditions: list[str] = Field(default_factory=list)


class MacroBreakdown(BaseModel):
    """Macronutrient content — of a meal, a day's intake, or what's remaining."""

    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float

    def __add__(self, other: "MacroBreakdown") -> "MacroBreakdown":
        return MacroBreakdown(
            kcal=self.kcal + other.kcal,
            protein_g=self.protein_g + other.protein_g,
            carbs_g=self.carbs_g + other.carbs_g,
            fat_g=self.fat_g + other.fat_g,
        )

    @classmethod
    def zero(cls) -> "MacroBreakdown":
        return cls(kcal=0, protein_g=0, carbs_g=0, fat_g=0)


class Meal(BaseModel):
    """A logged meal and its estimated macros, from a photo or a text description."""

    id: str
    user_id: str
    timestamp: datetime
    description: str
    source: Literal["photo", "text"]
    macros: MacroBreakdown
    confidence: float = 0.5  # estimator's confidence, 0..1


class NutritionTargets(BaseModel):
    """A user's daily macro targets (derived from profile, user-adjustable)."""

    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float


class DailyNutritionLedger(BaseModel):
    """Targets vs. what's been consumed today, and what's left to hit them."""

    targets: NutritionTargets
    consumed: MacroBreakdown

    def remaining(self) -> MacroBreakdown:
        """What's left toward target (negative when the user is over)."""
        return MacroBreakdown(
            kcal=self.targets.kcal - self.consumed.kcal,
            protein_g=self.targets.protein_g - self.consumed.protein_g,
            carbs_g=self.targets.carbs_g - self.consumed.carbs_g,
            fat_g=self.targets.fat_g - self.consumed.fat_g,
        )


class WorkoutLog(BaseModel):
    """A workout the user did — logged manually or detected from the device."""

    user_id: str
    date: Date
    type: str  # running, strength, yoga, cycling, ...
    duration_min: int
    source: Literal["manual", "device"] = "manual"


class ActivitySummary(BaseModel):
    """Computed view of recent activity — drives streaks and movement coaching."""

    days_worked_out_this_week: int
    current_streak: int
    steps_today: int
    steps_7d_avg: float
    active_minutes: int


class OnboardingState(BaseModel):
    """Where a user is in the conversational onboarding flow, plus answers so far."""

    user_id: str
    step: str
    data: dict = Field(default_factory=dict)
    complete: bool = False


class EvidenceSnippet(BaseModel):
    """A curated, citable piece of evidence the coach can ground claims in."""

    id: str
    topic: str
    text: str
    citation: str


class TriageOutcome(BaseModel):
    """The result of triaging a day's deviations."""

    route: TriageRoute
    deviations: list[Deviation] = Field(default_factory=list)
    rationale: str = ""
    pretest_probability: float | None = None


class Insight(BaseModel):
    """A generated, grounded coaching message and its provenance."""

    user_id: str
    date: Date
    message: str
    route: TriageRoute
    deviations: list[Deviation] = Field(default_factory=list)
    evidence_citations: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utcnow)


class ChatMessage(BaseModel):
    role: Literal["user", "coach"]
    text: str
    timestamp: datetime = Field(default_factory=utcnow)
