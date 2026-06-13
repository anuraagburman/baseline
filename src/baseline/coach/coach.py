"""The coaching engine — assembles context and delegates to the LLM.

``Coach`` is the single entry point for both daily insight generation and
follow-up conversation. It is LLM-agnostic (works with MockLLM or ClaudeClient)
and retriever-agnostic (works with SimpleEvidenceRetriever or a vector store).
"""

from __future__ import annotations

from datetime import date as Date

from baseline.coach.llm import LLMClient, build_llm_client
from baseline.coach.prompt import CoachContext
from baseline.coach.retriever import Retriever, SimpleEvidenceRetriever
from baseline.domain.models import (
    ActivitySummary,
    DailyNutritionLedger,
    Deviation,
    Insight,
    Meal,
    TriageRoute,
    UserProfile,
)


class Coach:
    def __init__(
        self,
        llm: LLMClient | None = None,
        retriever: Retriever | None = None,
    ) -> None:
        if llm is None:
            from baseline.config import get_settings
            s = get_settings()
            llm = build_llm_client(s.llm_provider, s.claude_model, s.anthropic_api_key)
        self._llm = llm
        self._retriever = retriever or SimpleEvidenceRetriever()

    def _topics(self, deviations: list[Deviation], profile: UserProfile) -> list[str]:
        topics = [d.metric for d in deviations]
        topics.append(profile.goal.value)
        return topics

    def generate_insight(
        self,
        profile: UserProfile,
        route: TriageRoute,
        deviations: list[Deviation],
        *,
        today_summary: str,
        date: Date,
        cold_start: bool = False,
    ) -> Insight:
        evidence = self._retriever.retrieve(self._topics(deviations, profile), k=2)
        context = CoachContext(
            profile=profile,
            route=route,
            deviations=deviations,
            today_summary=today_summary,
            evidence=evidence,
            cold_start=cold_start,
        )
        message = self._llm.generate(context)
        return Insight(
            user_id=profile.user_id,
            date=date,
            message=message,
            route=route,
            deviations=deviations,
            evidence_citations=[s.citation for s in evidence],
        )

    def answer_question(
        self,
        profile: UserProfile,
        deviations: list[Deviation],
        *,
        today_summary: str,
        question: str,
        cold_start: bool = False,
    ) -> str:
        evidence = self._retriever.retrieve(self._topics(deviations, profile), k=2)
        context = CoachContext(
            profile=profile,
            route=TriageRoute.COACH,
            deviations=deviations,
            today_summary=today_summary,
            evidence=evidence,
            cold_start=cold_start,
            user_message=question,
        )
        return self._llm.generate(context)

    # --- Structured confirmations (deterministic + numerically faithful) ---
    # These are factual confirmations, not open coaching, so they are built from
    # the data directly: a message can never cite a macro the ledger doesn't have.

    def nutrition_reply(
        self, profile: UserProfile, meal: Meal, ledger: DailyNutritionLedger
    ) -> str:
        m = meal.macros
        remaining = ledger.remaining()
        protein_left = int(round(remaining.protein_g))
        kcal_left = int(round(remaining.kcal))

        parts = [
            f"Logged {meal.description}: ~{int(round(m.protein_g))}g protein, "
            f"{int(round(m.carbs_g))}g carbs, {int(round(m.fat_g))}g fat "
            f"({int(round(m.kcal))} kcal)."
        ]
        if remaining.protein_g <= 0:
            parts.append(
                f"You've hit your protein goal for today 🎯 "
                f"and have {max(kcal_left, 0)} kcal left."
            )
        else:
            parts.append(
                f"You have {protein_left}g protein and {max(kcal_left, 0)} kcal "
                f"left toward today's goal."
            )
        if meal.confidence < 0.5:
            parts.append("(Rough estimate — reply with details to refine it.)")
        return " ".join(parts)

    def activity_reply(self, profile: UserProfile, summary: ActivitySummary) -> str:
        steps = summary.steps_today
        if summary.current_streak >= 2:
            opener = (
                f"Nice work — that's a {summary.current_streak}-day streak 🔥 and "
                f"{summary.days_worked_out_this_week} workouts this week."
            )
        elif summary.current_streak == 1:
            opener = (
                f"Great start — that's {summary.days_worked_out_this_week} "
                f"workout(s) this week. Go again tomorrow to build a streak."
            )
        else:
            opener = (
                f"No workout logged yet today — an easy session would get your "
                f"streak going. You're at {summary.days_worked_out_this_week} this week."
            )
        return f"{opener} {steps} steps so far today (7-day average {int(round(summary.steps_7d_avg))})."
