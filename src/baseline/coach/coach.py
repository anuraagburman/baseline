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
    Deviation,
    Insight,
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
