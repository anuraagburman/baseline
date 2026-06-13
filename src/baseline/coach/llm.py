"""LLM client interface and implementations.

v1 ships two implementations behind the ``LLMClient`` protocol:

- :class:`MockLLM` — fully deterministic, no API key needed. It constructs a
  plausible, grounded coaching message directly from the ``CoachContext`` using
  the same ``frame_deviation`` function the real prompt uses. This means the
  whole pipeline (including the eval harness) runs and is testable offline.

- :class:`ClaudeClient` — the real Anthropic API (claude-opus-4-8 by default).
  Swapping to it is: ``BASELINE_LLM_PROVIDER=claude`` + ``ANTHROPIC_API_KEY``.

Nothing else in the codebase imports from ``anthropic`` directly; that import
lives only here behind the client, so the rest of the system has no hard
dependency on the SDK.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from baseline.coach.prompt import (
    SYSTEM_PROMPT,
    CoachContext,
    METRIC_LABELS,
    frame_deviation,
    render_user_prompt,
)
from baseline.domain.models import TriageRoute


@runtime_checkable
class LLMClient(Protocol):
    def generate(self, context: CoachContext) -> str:
        """Generate a grounded coaching message from the assembled context."""
        ...


class MockLLM:
    """A deterministic LLM that constructs coaching messages from context.

    It never makes network calls and always produces the same output for the
    same input, which makes the eval harness reproducible and the full pipeline
    runnable with no API key.
    """

    def generate(self, context: CoachContext) -> str:
        p = context.profile
        goal_label = p.goal.value.replace("_", " ")
        lines: list[str] = []

        if context.route is TriageRoute.MONITOR:
            lines.append(
                f"Good day, {p.name or 'there'}! Everything looks within your normal range today."
            )
            lines.append(
                f"Keep doing what you're doing — consistency is the real driver for {goal_label}."
            )
            lines.append("(Not medical advice.)")
            return " ".join(lines)

        if context.route is TriageRoute.ESCALATE:
            if context.deviations:
                dev_text = frame_deviation(context.deviations[0])
            else:
                dev_text = "some patterns in your data"
            lines.append(
                f"Heads up: I'm seeing {dev_text}, and given your profile, "
                "it may be worth discussing this with a doctor — not as an alarm, "
                "just a heads-up worth mentioning at your next check-in."
            )
            lines.append("(This is not medical advice or a diagnosis.)")
            return " ".join(lines)

        # COACH route — build a deviation-framed, action-oriented message.
        if context.deviations:
            top = context.deviations[0]
            framed = frame_deviation(top)
            metric_label = METRIC_LABELS.get(top.metric, top.metric)
            lines.append(f"Today I noticed your {framed}.")
            if top.sustained:
                lines.append(f"This has been a pattern over the last few days.")
            # Evidence citation if available.
            if context.evidence:
                snippet = context.evidence[0]
                lines.append(snippet.text)
                lines.append(f"[{snippet.citation}]")
            # Goal-specific action suggestion.
            if goal_label == "lose fat":
                lines.append(
                    f"For your {goal_label} goal, focus on keeping sleep and recovery "
                    f"consistent — they directly support your body's ability to manage weight."
                )
            elif goal_label == "sleep better":
                lines.append(
                    f"A consistent bedtime is one of the highest-leverage levers you have "
                    f"right now for improving {metric_label}."
                )
            else:
                lines.append(
                    f"One thing that reliably helps {metric_label} return toward your usual: "
                    f"a restful night and a lighter day tomorrow."
                )
        else:
            lines.append(
                f"Your data looks broadly normal today, {p.name or 'there'}."
            )
        lines.append("(Not medical advice.)")

        if context.user_message:
            lines.insert(0, f"You asked: \"{context.user_message}\". ")

        return " ".join(lines)


class ClaudeClient:
    """Real Anthropic API client (claude-opus-4-8 by default)."""

    def __init__(self, model: str = "claude-opus-4-8", api_key: str | None = None) -> None:
        import anthropic  # imported here so SDK is not a hard dependency at import time

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def generate(self, context: CoachContext) -> str:
        import anthropic

        user_prompt = render_user_prompt(context)
        response = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text.strip()


def build_llm_client(provider: str, model: str, api_key: str | None) -> LLMClient:
    """Factory — reads from config and returns the right implementation."""
    if provider == "claude":
        return ClaudeClient(model=model, api_key=api_key)
    return MockLLM()
