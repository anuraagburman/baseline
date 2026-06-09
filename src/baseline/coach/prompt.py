"""The coach's system prompt, structured context, and prompt rendering.

``frame_deviation`` is the single source of the "X above your usual Y" framing.
Both the rendered prompt (what a real LLM sees) and the deterministic MockLLM
draw their numbers from it, so a coach message can never cite a number that is
not in the grounding context — the property the faithfulness eval enforces.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from baseline.domain.models import (
    Deviation,
    EvidenceSnippet,
    TriageRoute,
    UserProfile,
)

# Friendly, plain-language names for raw metric keys.
METRIC_LABELS = {
    "rhr": "resting heart rate",
    "hrv": "heart-rate variability",
    "sleep_mins": "sleep",
    "spo2": "blood oxygen",
    "resp_rate": "breathing rate",
    "steps": "steps",
    "active_zone_mins": "active minutes",
    "calories_out": "energy burned",
}

SYSTEM_PROMPT = """You are Baseline, a calm, prevention-first health coach.

Hard rules — never break these:
- You are NOT a doctor and this is NOT medical advice. Say so when relevant.
- NEVER diagnose, name a disease as the cause, or imply the user has a condition.
  Do not diagnose under any circumstances.
- Ground every claim in the user's OWN data, framed as a deviation from their
  personal usual (e.g. "6 bpm above your usual"). Never invent numbers.
- Recommend only modifiable behaviours (sleep, movement, activity, nutrition,
  recovery). No medication, no clinical instructions.
- Stay calm and non-alarming. One clear, actionable suggestion is better than a
  list. Tie advice to the user's stated goal.
- If something is genuinely worth professional attention, gently suggest
  "it may be worth discussing with a doctor" — never state a conclusion.
- If the personal baseline is still forming (cold start), say you are still
  learning their normal and avoid over-claiming.
"""


@dataclass
class CoachContext:
    """Everything the coach needs to ground one message."""

    profile: UserProfile
    route: TriageRoute
    deviations: list[Deviation] = field(default_factory=list)
    today_summary: str = ""
    evidence: list[EvidenceSnippet] = field(default_factory=list)
    cold_start: bool = False
    user_message: str | None = None


def frame_deviation(dev: Deviation) -> str:
    """Render a deviation in plain, self-referential language with a friendly label."""
    label = METRIC_LABELS.get(dev.metric, dev.metric)
    return dev.describe().replace(dev.metric, label, 1)


def render_user_prompt(context: CoachContext) -> str:
    """Assemble the grounding context into the user-turn prompt for an LLM."""
    p = context.profile
    lines: list[str] = []
    lines.append(f"GOAL: {p.goal.value}")
    lines.append(f"PROFILE: age {p.age}, {p.sex.value}, {p.weight_kg:.0f} kg")
    lines.append(f"TRIAGE ROUTE: {context.route.value}")
    if context.cold_start:
        lines.append("NOTE: Baseline is still learning this user's normal (cold start).")

    lines.append("")
    lines.append(f"TODAY: {context.today_summary}")

    lines.append("")
    if context.deviations:
        lines.append("WHAT STANDS OUT VS USUAL:")
        for dev in context.deviations:
            tag = " (sustained)" if dev.sustained else ""
            lines.append(f"- {frame_deviation(dev)}{tag}")
    else:
        lines.append("WHAT STANDS OUT VS USUAL: nothing notable today.")

    if context.evidence:
        lines.append("")
        lines.append("RELEVANT EVIDENCE (cite where used):")
        for s in context.evidence:
            lines.append(f"- {s.text} [{s.citation}]")

    lines.append("")
    if context.user_message:
        lines.append(f"USER QUESTION: {context.user_message}")
        lines.append("Answer the question, grounded in the data above.")
    else:
        lines.append(
            "Write today's single, calm, actionable coaching message for this user."
        )

    return "\n".join(lines)
