"""Terminal chat loop for demoing Baseline without a frontend.

Usage:
    python -m baseline.cli

No API key needed (runs with MockLLM by default). To use real Claude:
    BASELINE_LLM_PROVIDER=claude ANTHROPIC_API_KEY=sk-... python -m baseline.cli
"""

from __future__ import annotations

import sys


def _ask(prompt: str, options: list[str]) -> str:
    print(f"\n{prompt}")
    for i, opt in enumerate(options, 1):
        print(f"  [{i}] {opt}")
    while True:
        choice = input("→ ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1]
        print("  Please enter a number.")


def main() -> None:
    from baseline.coach.coach import Coach
    from baseline.coach.llm import build_llm_client
    from baseline.coach.retriever import SimpleEvidenceRetriever
    from baseline.config import get_settings
    from baseline.conversation.manager import ConversationManager
    from baseline.domain.models import Goal, Sex
    from baseline.onboarding.flow import OnboardingRequest, onboard_user
    from baseline.sources.synthetic import SyntheticHealthSource
    from baseline.storage.db import Database

    cfg = get_settings()
    db = Database(cfg.db_url)
    db.create_all()
    llm = build_llm_client(cfg.llm_provider, cfg.claude_model, cfg.anthropic_api_key)
    coach = Coach(llm=llm, retriever=SimpleEvidenceRetriever())
    mgr = ConversationManager(coach=coach)
    source = SyntheticHealthSource()

    print("\n" + "=" * 60)
    print("  BASELINE CHAT  — prevention-first AI health coach")
    print("=" * 60)
    print("  (Not medical advice. Type 'quit' to exit.)\n")

    user_id = input("Your user ID (hit Enter for 'demo'): ").strip() or "demo"

    goal_raw = _ask("What's your main goal right now?",
                    ["lose_fat", "sleep_better", "more_energy", "general_health"])
    sex_raw = _ask("Sex (for population-norm cold-start fallback):",
                   ["male", "female", "other"])

    try:
        age = int(input("Age: ").strip())
    except ValueError:
        age = 35

    try:
        weight = float(input("Weight in kg: ").strip())
    except ValueError:
        weight = 70.0

    print("\nOnboarding — pulling your last 45 days of data… ", end="", flush=True)
    result = onboard_user(
        db, source, coach,
        OnboardingRequest(
            user_id=user_id, name=None, age=age,
            sex=Sex(sex_raw), weight_kg=weight, goal=Goal(goal_raw),
            backfill_days=cfg.backfill_days,
        ),
    )
    print("done.\n")

    insight = result.first_insight
    mgr.set_last_insight(user_id, insight, today_summary="Generated at onboarding.")

    print("─" * 60)
    print("YOUR FIRST INSIGHT")
    print("─" * 60)
    print(insight.message)
    print(f"\n  [route: {insight.route.value}]")
    if insight.evidence_citations:
        print("  Evidence:")
        for c in insight.evidence_citations:
            print(f"    • {c}")
    print("─" * 60)
    print("\nYou can now chat with Baseline. Try asking 'why?' or 'what should I do tonight?'")
    print("Type 'quit' to exit.\n")

    profile = result.profile
    while True:
        try:
            msg = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if not msg:
            continue
        if msg.lower() in {"quit", "exit", "q"}:
            print("Goodbye!")
            break

        reply = mgr.chat(user_id, profile, msg)
        print(f"\nBaseline: {reply}\n")


if __name__ == "__main__":
    main()
