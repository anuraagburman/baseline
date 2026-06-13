"""FastAPI application.

``build_app`` is the factory used by tests (so each test gets an isolated DB)
and by the CLI runner. The ``lifespan`` context initialises all singletons
(DB schema, coach, conversation manager) once at startup.

Endpoints:
  POST /onboard              — profile + backfill + first insight
  GET  /daily-insight/{uid}  — compute and return today's coaching insight
  POST /chat/{uid}           — conversation turn
  GET  /history/{uid}        — raw metrics (the private "app-side" view)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

import fastapi
from fastapi import FastAPI, HTTPException

from baseline.analytics.baseline_engine import BaselineConfig, compute_deviations
from baseline.api.schemas import (
    ChatRequest,
    ChatResponse,
    DailyInsightResponse,
    HistoryResponse,
    OnboardRequest,
    OnboardResponse,
    InsightResponse,
)
from baseline.coach.coach import Coach
from baseline.coach.llm import build_llm_client
from baseline.coach.retriever import SimpleEvidenceRetriever
from baseline.conversation.manager import ConversationManager
from baseline.domain.models import Goal, Sex, UserProfile
from baseline.onboarding.flow import OnboardingRequest, onboard_user
from baseline.sources.synthetic import SyntheticHealthSource
from baseline.storage import repository as repo
from baseline.storage.db import Database
from baseline.triage.engine import triage
from baseline.triage.rules import TriageConfig


def build_app(
    db_url: str = "sqlite:///baseline.db",
    llm_provider: str = "mock",
    claude_model: str = "claude-opus-4-8",
    anthropic_api_key: str | None = None,
) -> FastAPI:
    db = Database(db_url)
    db.create_all()  # idempotent — safe to call at startup every time
    coach = Coach(
        llm=build_llm_client(llm_provider, claude_model, anthropic_api_key),
        retriever=SimpleEvidenceRetriever(),
    )
    conversation = ConversationManager(coach=coach)
    source = SyntheticHealthSource()

    app = FastAPI(title="Baseline Chat")

    @app.post("/onboard", response_model=OnboardResponse)
    async def onboard(req: OnboardRequest):
        result = onboard_user(
            db, source, coach,
            OnboardingRequest(
                user_id=req.user_id,
                name=req.name,
                age=req.age,
                sex=Sex(req.sex),
                weight_kg=req.weight_kg,
                goal=Goal(req.goal),
                delivery_pref=req.delivery_pref,
                backfill_days=req.backfill_days,
            ),
        )
        insight = result.first_insight
        conversation.set_last_insight(req.user_id, insight, today_summary=_summary(db, req.user_id))
        return OnboardResponse(
            user_id=req.user_id,
            first_insight=InsightResponse(
                user_id=insight.user_id,
                date=insight.date,
                message=insight.message,
                route=insight.route.value,
                evidence_citations=insight.evidence_citations,
                generated_at=insight.generated_at,
            ),
        )

    @app.get("/daily-insight/{user_id}", response_model=DailyInsightResponse)
    async def daily_insight(user_id: str):
        with db.session() as s:
            profile = repo.get_user(s, user_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="User not found — complete onboarding first.")

        with db.session() as s:
            recent = repo.get_recent_metrics(s, user_id, 60)

        if not recent:
            raise HTTPException(status_code=404, detail="No data found for user.")

        series = sorted(recent, key=lambda m: m.date)
        deviations = compute_deviations(series, profile=profile, config=BaselineConfig())
        cold_start = len(series) < BaselineConfig().min_history_days
        triage_out = triage(deviations, profile=profile, config=TriageConfig())

        today_summary = series[-1].summary()
        insight = coach.generate_insight(
            profile, triage_out.route, triage_out.deviations,
            today_summary=today_summary,
            date=date.today(),
            cold_start=cold_start,
        )
        with db.session() as s:
            repo.save_insight(s, insight)

        conversation.set_last_insight(user_id, insight, today_summary=today_summary)

        return DailyInsightResponse(
            user_id=insight.user_id,
            date=insight.date,
            message=insight.message,
            route=insight.route.value,
            evidence_citations=insight.evidence_citations,
        )

    @app.post("/chat/{user_id}", response_model=ChatResponse)
    async def chat(user_id: str, req: ChatRequest):
        with db.session() as s:
            profile = repo.get_user(s, user_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="User not found — complete onboarding first.")

        reply = conversation.chat(user_id, profile, req.message)
        return ChatResponse(reply=reply)

    @app.get("/history/{user_id}", response_model=HistoryResponse)
    async def history(user_id: str):
        with db.session() as s:
            metrics = repo.get_recent_metrics(s, user_id, 60)
        # Return oldest → newest and expose full metrics (the "private app-side" view).
        ordered = sorted(metrics, key=lambda m: m.date)
        return HistoryResponse(
            user_id=user_id,
            metrics=[m.model_dump(mode="json") for m in ordered],
        )

    return app


def _summary(db: Database, user_id: str) -> str:
    with db.session() as s:
        recent = repo.get_recent_metrics(s, user_id, 1)
    return recent[0].summary() if recent else "No data yet."


def create_app() -> FastAPI:
    """Entry point for ``uvicorn baseline.api.app:create_app`` (production)."""
    from baseline.config import get_settings
    s = get_settings()
    return build_app(
        db_url=s.db_url,
        llm_provider=s.llm_provider,
        claude_model=s.claude_model,
        anthropic_api_key=s.anthropic_api_key,
    )
