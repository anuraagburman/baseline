"""Conversation manager — the top-level inbound dispatcher.

Routes every inbound message to the right handler:
  1. Sensitivity guard — never expose raw clinical data in chat
  2. Onboarding gate — mid-flow users are routed to the FSM
  3. Image → food log → macro reply
  4. Food text intent → estimator → log → macro reply
  5. Workout intent → log → activity reply
  6. "Why?" / coaching → v1 coach brain

All intent routing is deterministic keyword-based; clean injection of all
dependencies so tests never touch network or disk.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date

from baseline.channels.base import InboundMessage
from baseline.coach.coach import Coach
from baseline.domain.models import (
    ChatMessage, Insight, TriageRoute, UserProfile, WorkoutLog,
)

# ----- Sensitivity guard -----
_SENSITIVITY_TRIGGERS = [
    "raw data", "raw metrics", "full trend", "all my metric",
    "dump my", "show me all", "escalation detail", "clinical",
    "show me the numbers", "all my data",
]
_SENSITIVITY_REPLY = (
    "That level of detail — your raw metrics and full trends — lives in your "
    "private data screen in the app, not here in chat. Head there for the "
    "full picture. Can I help you with anything else today?"
)
_ESCALATION_DETAIL_REPLY = (
    "The clinical detail and escalation path are in your private data screen, "
    "not in chat. If something felt urgent, please speak with a doctor directly."
)

# ----- Intent keywords -----
_WHY_TRIGGERS = {"why", "why?", "explain", "reason", "how come", "tell me why"}
_FOOD_TRIGGERS = {"ate", "had", "logged", "just ate", "breakfast", "lunch", "dinner",
                  "snack", "calories", "kcal", "protein", "just had", "eaten", "drink",
                  "drank", "meal", "ate a", "just finished eating"}
_WORKOUT_TRIGGERS = {"worked out", "ran", "gym", "lifted", "yoga", "cycling", "trained",
                     "just finished", "ran for", "run", "swimming", "hiit", "workout",
                     "exercise", "played", "walked for"}

_NO_INSIGHT_REPLY = (
    "I haven't generated your daily insight yet. Ask anything or say 'go' "
    "to analyse your recent data."
)

# ----- Opt-out / opt-in (WhatsApp STOP/START convention) -----
_STOP_TRIGGERS = {"stop", "pause", "unsubscribe", "cancel", "quit", "end"}
_START_TRIGGERS = {"start", "resume", "subscribe"}
_STOP_REPLY = (
    "Got it — I've paused your daily messages. You won't hear from me unless you "
    "message first. Say \"start\" anytime to turn them back on. 👋"
)
_START_REPLY = (
    "You're back on — I'll send your daily check-in again. 👋"
)

# Friendly catch-all so no message ever dead-ends in silence.
_FALLBACK_REPLY = (
    "I'm your health coach 👋 You can: send a photo of a meal (or describe it) to "
    "log calories and protein, tell me about a workout, or ask \"why?\" about today's "
    "tip. What would you like to do?"
)


def _is_intent(msg_lower: str, triggers: set[str]) -> bool:
    return any(t in msg_lower for t in triggers)


def _parse_workout_from_text(text: str) -> tuple[str, int]:
    """Extract (type, duration_min) from a natural-language workout description."""
    t = text.lower()
    duration = 30  # default
    m = re.search(r"(\d+)\s*(min|minute|hour|hr)\b", t)
    if m:
        val = int(m.group(1))
        duration = val * 60 if "hour" in m.group(2) or "hr" in m.group(2) else val

    for keyword in ("ran", "run", "running"):
        if keyword in t:
            return "running", duration
    for keyword in ("gym", "lift", "lifted", "strength"):
        if keyword in t:
            return "strength", duration
    for keyword in ("yoga",):
        if keyword in t:
            return "yoga", duration
    for keyword in ("cycling", "bike", "biked"):
        if keyword in t:
            return "cycling", duration
    for keyword in ("swim", "swimming"):
        if keyword in t:
            return "swimming", duration
    for keyword in ("hiit",):
        if keyword in t:
            return "hiit", duration
    for keyword in ("walk", "walked"):
        if keyword in t:
            return "walking", duration
    return "workout", duration


@dataclass
class _UserSession:
    last_insight: Insight | None = None
    today_summary: str = ""
    history: list[ChatMessage] = field(default_factory=list)
    onboarding_data: dict = field(default_factory=dict)


class ConversationManager:
    """The top-level message dispatcher.

    Injected dependencies (all have deterministic mock defaults):
      ``coach``           — generates coaching insights + nutrition/activity replies
      ``db``              — SQLAlchemy Database (for persisting meals/workouts/state)
      ``estimator``       — converts food text/image to macros
      ``onboarding_fsm``  — multi-step conversational onboarding
      ``source``          — HealthSource for post-onboarding backfill
    """

    def __init__(
        self,
        coach: Coach | None = None,
        db=None,
        estimator=None,
        onboarding_fsm=None,
        source=None,
        oauth_provider=None,
        public_base_url: str = "http://localhost:8000",
    ) -> None:
        self._coach = coach or Coach()
        self._db = db
        self._estimator = estimator
        self._fsm = onboarding_fsm
        self._source = source
        self._oauth = oauth_provider
        self._public_base_url = public_base_url.rstrip("/")
        self._sessions: dict[str, _UserSession] = {}

    def set_last_insight(self, user_id: str, insight: Insight, today_summary: str) -> None:
        sess = self._sessions.setdefault(user_id, _UserSession())
        sess.last_insight = insight
        sess.today_summary = today_summary

    def history(self, user_id: str) -> list[ChatMessage]:
        return self._sessions.get(user_id, _UserSession()).history

    # --- Public entry points ---

    def handle(self, inbound: InboundMessage, profile: UserProfile) -> str:
        """Route any inbound message to the correct handler."""
        sess = self._sessions.setdefault(inbound.user_id, _UserSession())
        reply = self._dispatch(inbound, profile, sess)
        sess.history.append(ChatMessage(role="user",
                                        text=inbound.text or "[media]"))
        sess.history.append(ChatMessage(role="coach", text=reply))
        return reply

    def chat(self, user_id: str, profile: UserProfile, message: str) -> str:
        """Convenience wrapper for text-only callers (v1 API compat)."""
        return self.handle(InboundMessage(user_id=user_id, text=message), profile)

    # --- Internal dispatch ---

    def _dispatch(self, inbound: InboundMessage, profile: UserProfile,
                  sess: _UserSession) -> str:
        msg = inbound.text or ""
        msg_lower = msg.lower()

        # 1) Sensitivity guard (always first)
        if any(t in msg_lower for t in _SENSITIVITY_TRIGGERS):
            return _SENSITIVITY_REPLY
        if (sess.last_insight and sess.last_insight.route is TriageRoute.ESCALATE
                and ("escalat" in msg_lower or "detail" in msg_lower)):
            return _ESCALATION_DETAIL_REPLY

        # 1b) Stop / start — toggle proactive-message consent (works anytime)
        stripped = msg_lower.strip().strip(".!")
        if stripped in _STOP_TRIGGERS:
            self._set_opt_in(inbound.user_id, False)
            return _STOP_REPLY
        if stripped in _START_TRIGGERS:
            self._set_opt_in(inbound.user_id, True)
            return _START_REPLY

        # 2) Onboarding gate
        if self._db and self._fsm:
            from baseline.storage import repository as repo
            with self._db.session() as s:
                ob_state = repo.get_onboarding_state(s, inbound.user_id)
            if ob_state is None or not ob_state.complete:
                return self._handle_onboarding(inbound, profile, sess, ob_state)

        # 3) Image → food log
        if inbound.has_media and self._estimator and self._db:
            return self._handle_food_image(inbound, profile)

        # 4) Food text intent
        if _is_intent(msg_lower, _FOOD_TRIGGERS) and self._estimator and self._db:
            return self._handle_food_text(msg, profile)

        # 5) Workout intent
        if _is_intent(msg_lower, _WORKOUT_TRIGGERS) and self._db:
            return self._handle_workout(msg, profile)

        # 6) "Why?" / coaching
        is_why = _is_intent(msg_lower, _WHY_TRIGGERS)
        if is_why and sess.last_insight and sess.last_insight.deviations:
            return self._coach.answer_question(
                profile, sess.last_insight.deviations,
                today_summary=sess.today_summary, question=msg,
            )

        # 7) Greeting / help → capability menu (so the user always knows what to do)
        if (stripped in {"hi", "hello", "hey", "help", "menu", "start over", "?"}
                or "what can you" in msg_lower or "how does this work" in msg_lower
                or msg_lower.startswith("help")):
            return _FALLBACK_REPLY

        # 8) Genuine free-form question → coach brain (always returns a grounded reply)
        if msg.strip():
            devs = sess.last_insight.deviations if sess.last_insight else []
            summary = sess.today_summary or "No data yet."
            return self._coach.answer_question(profile, devs, today_summary=summary, question=msg)

        # 9) Empty / unparseable → friendly capability menu (never dead-end)
        return _FALLBACK_REPLY

    def _set_opt_in(self, user_id: str, value: bool) -> None:
        if not self._db:
            return
        from baseline.storage import repository as repo
        with self._db.session() as s:
            p = repo.get_user(s, user_id)
            if p is not None:
                p.opted_in = value
                repo.upsert_user(s, p)

    def _handle_onboarding(self, inbound: InboundMessage, profile: UserProfile,
                           sess: _UserSession, ob_state) -> str:
        from baseline.storage import repository as repo
        from baseline.domain.models import OnboardingState

        if ob_state is None:
            result = self._fsm.start(inbound.user_id)
        else:
            result = self._fsm.handle(ob_state, inbound.text or "")

        with self._db.session() as s:
            repo.save_onboarding_state(s, result.state)

        if result.complete and result.assembled and self._source:
            self._finalize_onboarding(inbound.user_id, result.assembled, profile, sess)

        # At the connect step, append a real, tappable Google OAuth link (no key,
        # no password — just a login + consent). Falls back to synthetic data until
        # real Google credentials are configured.
        if (not result.complete and result.state.step == "connect" and self._oauth):
            redirect_uri = f"{self._public_base_url}/oauth/google/callback"
            url = self._oauth.authorization_url(inbound.user_id, redirect_uri)
            return f"{result.reply}\n\n👉 {url}"

        return result.reply

    def _finalize_onboarding(self, user_id: str, assembled: dict, profile: UserProfile,
                              sess: _UserSession) -> None:
        from baseline.onboarding.flow import onboard_user, OnboardingRequest
        from baseline.domain.models import Goal, Sex

        req = OnboardingRequest(
            user_id=user_id,
            name=assembled.get("name"),
            age=assembled.get("age") or profile.age,
            sex=Sex(assembled.get("sex") or profile.sex.value),
            weight_kg=assembled.get("weight_kg") or profile.weight_kg,
            goal=Goal(assembled.get("goal") or profile.goal.value),
            height_cm=assembled.get("height_cm"),
        )
        result = onboard_user(self._db, self._source, self._coach, req)
        # Persist the consent captured in the onboarding opt-in step.
        self._set_opt_in(user_id, bool(assembled.get("opted_in", False)))
        today_summary = result.first_insight.date.isoformat()
        self.set_last_insight(user_id, result.first_insight, today_summary)

    def _handle_food_image(self, inbound: InboundMessage, profile: UserProfile) -> str:
        from baseline.storage import repository as repo
        from baseline.analytics.nutrition import compute_ledger

        meal = self._estimator.from_image(
            inbound.user_id,
            inbound.media_bytes or b"",
            caption=inbound.caption,
        )
        with self._db.session() as s:
            repo.save_meal(s, meal)
            targets = repo.get_nutrition_targets(s, inbound.user_id)
            meals_today = repo.get_meals_for_day(s, inbound.user_id, date.today())

        if targets is None:
            return self._coach.nutrition_reply(profile, meal,
                                               __import__("baseline.domain.models",
                                                   fromlist=["DailyNutritionLedger",
                                                             "NutritionTargets",
                                                             "MacroBreakdown"])
                                               .DailyNutritionLedger(
                                                   targets=__import__("baseline.domain.models",
                                                       fromlist=["NutritionTargets"])
                                                   .NutritionTargets(kcal=2000, protein_g=130,
                                                                     carbs_g=200, fat_g=60),
                                                   consumed=meal.macros))
        ledger = compute_ledger(targets, meals_today)
        return self._coach.nutrition_reply(profile, meal, ledger)

    def _handle_food_text(self, text: str, profile: UserProfile) -> str:
        from baseline.storage import repository as repo
        from baseline.analytics.nutrition import compute_ledger

        meal = self._estimator.from_text(profile.user_id, text)
        with self._db.session() as s:
            repo.save_meal(s, meal)
            targets = repo.get_nutrition_targets(s, profile.user_id)
            meals_today = repo.get_meals_for_day(s, profile.user_id, date.today())

        from baseline.domain.models import DailyNutritionLedger, NutritionTargets, MacroBreakdown
        if targets is None:
            targets = NutritionTargets(kcal=2000, protein_g=130, carbs_g=200, fat_g=60)
        ledger = compute_ledger(targets, meals_today)
        return self._coach.nutrition_reply(profile, meal, ledger)

    def _handle_workout(self, text: str, profile: UserProfile) -> str:
        from baseline.storage import repository as repo
        from baseline.analytics.activity import summarize_activity

        workout_type, duration = _parse_workout_from_text(text)
        workout = WorkoutLog(user_id=profile.user_id, date=date.today(),
                             type=workout_type, duration_min=duration, source="manual")
        with self._db.session() as s:
            repo.log_workout(s, workout)
            workouts = repo.get_workouts_for_week(s, profile.user_id, date.today())
            recent_metrics = repo.get_recent_metrics(s, profile.user_id, 7)

        series = sorted(recent_metrics, key=lambda m: m.date)
        summary = summarize_activity(series, workouts, date.today())
        return self._coach.activity_reply(profile, summary)
