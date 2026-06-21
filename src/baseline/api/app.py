"""FastAPI application — v2 (food log, workout, OAuth, webhook, full router).

All endpoints use the same ConversationManager/Coach brain whether invoked via
the REST API, the CLI, or the WhatsApp webhook — identical code path everywhere.

Endpoints:
  POST /onboard                    profile + backfill + first insight
  GET  /daily-insight/{uid}        today's coaching insight
  POST /chat/{uid}                 conversation turn
  GET  /history/{uid}              raw metrics (private app-side view)
  POST /log-food/{uid}             text or file-upload → macro log → ledger
  POST /log-workout/{uid}          workout log → activity reply
  GET  /nutrition/{uid}            today's nutrition ledger
  GET  /activity/{uid}             today's activity summary
  POST /webhooks/whatsapp          Twilio inbound (mounted from webhooks.py)
  GET  /oauth/google/start/{uid}   begin Google Health connect flow
  GET  /oauth/google/callback      exchange code + store tokens
"""

from __future__ import annotations

from datetime import date

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from baseline.analytics.activity import summarize_activity
from baseline.analytics.baseline_engine import BaselineConfig, compute_deviations
from baseline.analytics.nutrition import compute_ledger, derive_targets
from baseline.api.schemas import (
    ChatRequest, ChatResponse, DailyInsightResponse,
    HistoryResponse, InsightResponse, OnboardRequest, OnboardResponse,
)
from baseline.channels.base import InboundMessage
from baseline.channels.local import LocalChannel
from baseline.coach.coach import Coach
from baseline.coach.llm import build_llm_client
from baseline.coach.retriever import SimpleEvidenceRetriever
from baseline.conversation.manager import ConversationManager
from baseline.domain.models import Goal, Sex, UserProfile, WorkoutLog
from baseline.nutrition.estimator import MockNutritionEstimator, build_nutrition_estimator
from baseline.onboarding.conversation import OnboardingFSM
from baseline.onboarding.flow import OnboardingRequest, onboard_user
from baseline.services.insights import compute_daily_insight
from baseline.sources.oauth import MockOAuthProvider, build_oauth_provider
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
    vision_provider: str = "mock",
    twilio_account_sid: str | None = None,
    twilio_auth_token: str | None = None,
    twilio_whatsapp_from: str = "whatsapp:+14155238886",
    google_client_id: str | None = None,
    google_client_secret: str | None = None,
) -> FastAPI:
    db = Database(db_url)
    db.create_all()

    coach = Coach(
        llm=build_llm_client(llm_provider, claude_model, anthropic_api_key),
        retriever=SimpleEvidenceRetriever(),
    )
    estimator = build_nutrition_estimator(vision_provider, claude_model, anthropic_api_key)
    source = SyntheticHealthSource()
    fsm = OnboardingFSM()

    # Channel: LocalChannel in dev/test, Twilio in prod.
    if twilio_account_sid and twilio_auth_token:
        from baseline.channels.twilio_whatsapp import TwilioWhatsAppChannel
        channel = TwilioWhatsAppChannel(
            account_sid=twilio_account_sid,
            auth_token=twilio_auth_token,
            from_number=twilio_whatsapp_from,
        )
    else:
        channel = LocalChannel()

    oauth_provider = build_oauth_provider(google_client_id, google_client_secret)

    manager = ConversationManager(
        coach=coach, db=db, estimator=estimator, onboarding_fsm=fsm, source=source,
    )

    app = FastAPI(title="Baseline Chat")

    # --- Mount sub-routers ---
    from baseline.api.webhooks import make_webhook_router
    from baseline.api.oauth import make_oauth_router

    app.include_router(make_webhook_router(manager, channel, db))
    app.include_router(make_oauth_router(oauth_provider, db, channel, twilio_whatsapp_from))

    # ---- Onboarding ----

    @app.post("/onboard", response_model=OnboardResponse)
    async def onboard(req: OnboardRequest):
        result = onboard_user(
            db, source, coach,
            OnboardingRequest(
                user_id=req.user_id, name=req.name, age=req.age,
                sex=Sex(req.sex), weight_kg=req.weight_kg,
                goal=Goal(req.goal), delivery_pref=req.delivery_pref,
                backfill_days=req.backfill_days,
            ),
        )
        insight = result.first_insight
        manager.set_last_insight(req.user_id, insight, today_summary=_today_summary(db, req.user_id))
        # Derive and store nutrition targets.
        with db.session() as s:
            profile = repo.get_user(s, req.user_id)
        if profile:
            targets = derive_targets(profile)
            with db.session() as s:
                repo.set_nutrition_targets(s, req.user_id, targets)
        # Mark onboarding complete.
        from baseline.domain.models import OnboardingState
        with db.session() as s:
            repo.save_onboarding_state(s, OnboardingState(
                user_id=req.user_id, step="done", data={}, complete=True))
        return OnboardResponse(
            user_id=req.user_id,
            first_insight=InsightResponse(
                user_id=insight.user_id, date=insight.date, message=insight.message,
                route=insight.route.value, evidence_citations=insight.evidence_citations,
                generated_at=insight.generated_at,
            ),
        )

    # ---- Daily insight ----

    @app.get("/daily-insight/{user_id}", response_model=DailyInsightResponse)
    async def daily_insight(user_id: str):
        with db.session() as s:
            profile = repo.get_user(s, user_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="User not found.")
        insight = compute_daily_insight(db, coach, user_id)
        if insight is None:
            raise HTTPException(status_code=404, detail="No data found.")
        manager.set_last_insight(user_id, insight, today_summary=insight.message)
        return DailyInsightResponse(
            user_id=insight.user_id, date=insight.date, message=insight.message,
            route=insight.route.value, evidence_citations=insight.evidence_citations,
        )

    # ---- Chat ----

    @app.post("/chat/{user_id}", response_model=ChatResponse)
    async def chat(user_id: str, req: ChatRequest):
        with db.session() as s:
            profile = repo.get_user(s, user_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="User not found.")
        reply = manager.chat(user_id, profile, req.message)
        return ChatResponse(reply=reply)

    # ---- History ----

    @app.get("/history/{user_id}", response_model=HistoryResponse)
    async def history(user_id: str):
        with db.session() as s:
            metrics = repo.get_recent_metrics(s, user_id, 60)
        ordered = sorted(metrics, key=lambda m: m.date)
        return HistoryResponse(user_id=user_id,
                               metrics=[m.model_dump(mode="json") for m in ordered])

    # ---- Food log ----

    @app.post("/log-food/{user_id}")
    async def log_food(
        user_id: str,
        text: str | None = Form(default=None),
        file: UploadFile | None = File(default=None),
    ):
        with db.session() as s:
            profile = repo.get_user(s, user_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="User not found.")

        if file is not None:
            image_bytes = await file.read()
            meal = estimator.from_image(user_id, image_bytes, caption=text)
        elif text:
            meal = estimator.from_text(user_id, text)
        else:
            raise HTTPException(status_code=422, detail="Provide 'text' or 'file'.")

        with db.session() as s:
            repo.save_meal(s, meal)
            targets = repo.get_nutrition_targets(s, user_id)
            meals_today = repo.get_meals_for_day(s, user_id, date.today())

        if targets is None:
            targets = derive_targets(profile)
        ledger = compute_ledger(targets, meals_today)
        return {
            "meal": meal.model_dump(mode="json"),
            "ledger_remaining": ledger.remaining().model_dump(mode="json"),
            "reply": coach.nutrition_reply(profile, meal, ledger),
        }

    # ---- Workout log ----

    @app.post("/log-workout/{user_id}")
    async def log_workout_endpoint(user_id: str, workout_type: str = Form(...),
                                   duration_min: int = Form(...)):
        with db.session() as s:
            profile = repo.get_user(s, user_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="User not found.")
        workout = WorkoutLog(user_id=user_id, date=date.today(),
                             type=workout_type, duration_min=duration_min)
        with db.session() as s:
            repo.log_workout(s, workout)
            workouts = repo.get_workouts_for_week(s, user_id, date.today())
            recent = repo.get_recent_metrics(s, user_id, 7)
        series = sorted(recent, key=lambda m: m.date)
        summary = summarize_activity(series, workouts, date.today())
        return {"reply": coach.activity_reply(profile, summary),
                "activity": summary.model_dump()}

    # ---- Nutrition ledger ----

    @app.get("/nutrition/{user_id}")
    async def get_nutrition(user_id: str):
        with db.session() as s:
            profile = repo.get_user(s, user_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="User not found.")
        with db.session() as s:
            targets = repo.get_nutrition_targets(s, user_id)
            meals_today = repo.get_meals_for_day(s, user_id, date.today())
        if targets is None:
            targets = derive_targets(profile)
        ledger = compute_ledger(targets, meals_today)
        return {
            "targets": targets.model_dump(),
            "consumed": ledger.consumed.model_dump(),
            "remaining": ledger.remaining().model_dump(),
        }

    # ---- Activity summary ----

    @app.get("/activity/{user_id}")
    async def get_activity(user_id: str):
        with db.session() as s:
            profile = repo.get_user(s, user_id)  # noqa: F841
        with db.session() as s:
            workouts = repo.get_workouts_for_week(s, user_id, date.today())
            recent = repo.get_recent_metrics(s, user_id, 7)
        series = sorted(recent, key=lambda m: m.date)
        summary = summarize_activity(series, workouts, date.today())
        return summary.model_dump()

    return app


def _today_summary(db: Database, user_id: str) -> str:
    with db.session() as s:
        recent = repo.get_recent_metrics(s, user_id, 1)
    return recent[0].summary() if recent else "No data yet."


def create_app() -> FastAPI:
    """Entry point for ``uvicorn baseline.api.app:create_app --factory``."""
    from baseline.config import get_settings
    s = get_settings()
    return build_app(
        db_url=s.db_url,
        llm_provider=s.llm_provider,
        claude_model=s.claude_model,
        anthropic_api_key=s.anthropic_api_key,
        vision_provider=s.vision_provider,
        twilio_account_sid=s.twilio_account_sid,
        twilio_auth_token=s.twilio_auth_token,
        twilio_whatsapp_from=s.twilio_whatsapp_from,
        google_client_id=s.google_client_id,
        google_client_secret=s.google_client_secret,
    )
