"""Terminal chat loop — drives the full ConversationManager, same path as the API.

Usage:
    python -m baseline.cli

No API key needed (runs with MockLLM by default). To use real Claude:
    BASELINE_LLM_PROVIDER=claude ANTHROPIC_API_KEY=sk-... python -m baseline.cli

Food photo: type the path to a local image file (e.g. /tmp/lunch.jpg) and the
estimator will treat it as a food photo and log the macros.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    from baseline.channels.base import InboundMessage
    from baseline.channels.local import LocalChannel
    from baseline.coach.coach import Coach
    from baseline.coach.llm import build_llm_client
    from baseline.coach.retriever import SimpleEvidenceRetriever
    from baseline.config import get_settings
    from baseline.conversation.manager import ConversationManager
    from baseline.domain.models import Goal, Sex
    from baseline.nutrition.estimator import build_nutrition_estimator
    from baseline.onboarding.conversation import OnboardingFSM
    from baseline.sources.synthetic import SyntheticHealthSource
    from baseline.storage import repository as repo
    from baseline.storage.db import Database

    cfg = get_settings()
    db = Database(cfg.db_url)
    db.create_all()

    llm = build_llm_client(cfg.llm_provider, cfg.claude_model, cfg.anthropic_api_key)
    estimator = build_nutrition_estimator(cfg.vision_provider, cfg.claude_model, cfg.anthropic_api_key)
    coach = Coach(llm=llm, retriever=SimpleEvidenceRetriever())
    fsm = OnboardingFSM()
    source = SyntheticHealthSource()
    mgr = ConversationManager(coach=coach, db=db, estimator=estimator,
                               onboarding_fsm=fsm, source=source)

    print("\n" + "=" * 60)
    print("  BASELINE CHAT  — prevention-first AI health coach")
    print("=" * 60)
    print("  (Not medical advice. Type 'quit' to exit.)")
    print("  Tip: type a file path like /tmp/lunch.jpg to log a food photo.\n")

    user_id = input("Your user ID (press Enter for 'demo'): ").strip() or "demo"

    # Get or create the profile.
    with db.session() as s:
        profile = repo.get_user(s, user_id)

    if profile is None:
        profile_stub = __import__("baseline.domain.models", fromlist=["UserProfile"]).UserProfile(
            user_id=user_id, age=30, sex=Sex.OTHER, weight_kg=70.0, goal=Goal.GENERAL_HEALTH,
        )
        with db.session() as s:
            repo.upsert_user(s, profile_stub)
        profile = profile_stub

    print(f"\nHello{' ' + profile.name if profile.name else ''}! Connecting to Baseline...\n")

    # Check onboarding state — if not complete, the FSM will handle it conversationally.
    with db.session() as s:
        ob_state = repo.get_onboarding_state(s, user_id)

    if ob_state is None or not ob_state.complete:
        # Kick off onboarding.
        result = fsm.start(user_id)
        with db.session() as s:
            repo.save_onboarding_state(s, result.state)
        print(f"Baseline: {result.reply}\n")
    else:
        print("Baseline: Welcome back! Type anything to chat.\n")

    while True:
        try:
            raw = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if not raw:
            continue
        if raw.lower() in {"quit", "exit", "q"}:
            print("Goodbye!")
            break

        # Detect file paths → food photo.
        path = Path(raw)
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} and path.exists():
            image_bytes = path.read_bytes()
            caption = input("  Caption (optional, press Enter to skip): ").strip() or None
            inbound = InboundMessage(user_id=user_id, text=None,
                                     media_bytes=image_bytes, caption=caption)
        else:
            inbound = InboundMessage(user_id=user_id, text=raw)

        # Re-fetch profile in case onboarding updated it.
        with db.session() as s:
            profile = repo.get_user(s, user_id) or profile

        reply = mgr.handle(inbound, profile)
        print(f"\nBaseline: {reply}\n")


if __name__ == "__main__":
    main()
