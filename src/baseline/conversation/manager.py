"""Conversation manager — session state, why-handling, and the privacy guard.

The manager sits between the user's raw chat message and the coach. It:
1. Maintains light session state (last insight, chat history) per user.
2. Routes "why?" questions to a grounded explanation using the driving deviation.
3. Enforces the two-tier privacy split from the PRD: chat carries interpretation
   and behaviour only. Requests for raw metrics, full trends, or escalation detail
   are deflected to the private app/web layer — sensitive data never surfaces in
   the chat body.
4. Falls back gracefully when there is no prior insight yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from baseline.coach.coach import Coach
from baseline.domain.models import ChatMessage, Insight, TriageRoute, UserProfile

# Phrases that indicate the user wants raw clinical payloads — deflect to app.
_SENSITIVITY_TRIGGERS = [
    "raw data",
    "raw metrics",
    "full trend",
    "all my metric",
    "dump my",
    "show me all",
    "escalation detail",
    "clinical",
    "show me the numbers",
    "all my data",
]

_WHY_TRIGGERS = {"why", "why?", "why is", "explain", "reason", "how come", "tell me why"}

_SENSITIVITY_REPLY = (
    "That level of detail — your raw metrics and full trends — lives in your "
    "private data screen in the app, not here in chat. Head there for the "
    "full picture. Can I help you with anything else today?"
)

_ESCALATION_DETAIL_REPLY = (
    "The clinical detail and escalation path are in your private data screen, "
    "not in chat. I want to keep that information where it's safe and complete. "
    "If something felt urgent, please don't hesitate to speak with a doctor directly."
)

_NO_INSIGHT_REPLY = (
    "I haven't generated your daily insight yet — usually that happens each "
    "morning or evening depending on your preference. Ask me anything else in "
    "the meantime, or say 'go' for me to analyse what I know about you so far."
)


@dataclass
class _UserSession:
    last_insight: Insight | None = None
    today_summary: str = ""
    history: list[ChatMessage] = field(default_factory=list)


class ConversationManager:
    def __init__(self, coach: Coach | None = None) -> None:
        self._coach = coach or Coach()
        self._sessions: dict[str, _UserSession] = {}

    def set_last_insight(
        self, user_id: str, insight: Insight, today_summary: str
    ) -> None:
        sess = self._sessions.setdefault(user_id, _UserSession())
        sess.last_insight = insight
        sess.today_summary = today_summary

    def history(self, user_id: str) -> list[ChatMessage]:
        return self._sessions.get(user_id, _UserSession()).history

    def chat(self, user_id: str, profile: UserProfile, message: str) -> str:
        sess = self._sessions.setdefault(user_id, _UserSession())
        sess.history.append(ChatMessage(role="user", text=message))

        reply = self._route(sess, profile, message)

        sess.history.append(ChatMessage(role="coach", text=reply))
        return reply

    def _route(self, sess: _UserSession, profile: UserProfile, message: str) -> str:
        msg_lower = message.lower()

        # 1) Sensitivity guard — deflect requests for raw clinical payloads.
        if any(trigger in msg_lower for trigger in _SENSITIVITY_TRIGGERS):
            return _SENSITIVITY_REPLY

        # 2) Escalation detail guard.
        if sess.last_insight and sess.last_insight.route is TriageRoute.ESCALATE:
            if "escalat" in msg_lower or "more about" in msg_lower or "detail" in msg_lower:
                return _ESCALATION_DETAIL_REPLY

        # 3) "Why?" — grounded explanation from the last insight's deviations.
        is_why = any(trigger in msg_lower for trigger in _WHY_TRIGGERS)
        if is_why and sess.last_insight and sess.last_insight.deviations:
            return self._coach.answer_question(
                profile,
                sess.last_insight.deviations,
                today_summary=sess.today_summary,
                question=message,
            )

        # 4) No prior insight yet — friendly orientation.
        if sess.last_insight is None:
            if any(g in msg_lower for g in ["hello", "hi", "hey", "how", "what"]):
                return _NO_INSIGHT_REPLY

        # 5) General free-form — delegate to the coach.
        deviations = sess.last_insight.deviations if sess.last_insight else []
        summary = sess.today_summary or "No data available yet."
        return self._coach.answer_question(
            profile, deviations, today_summary=summary, question=message
        )
