"""Onboarding: persist profile, backfill historical data, return a first insight.

Design principle: zero new app, instant payoff. Onboarding completes in a single
call and the caller receives a ready-to-deliver first-value insight (even if the
personal baseline is immature — cold-start path gives population-norm-grounded
orientation rather than silence).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from baseline.analytics.baseline_engine import BaselineConfig, compute_deviations
from baseline.coach.coach import Coach
from baseline.domain.models import Goal, Insight, Sex, TriageRoute, UserProfile
from baseline.ingestion.pipeline import ingest_range
from baseline.sources.base import HealthSource
from baseline.storage import repository as repo
from baseline.storage.db import Database
from baseline.triage.engine import triage
from baseline.triage.rules import TriageConfig


@dataclass
class OnboardingRequest:
    user_id: str
    name: str | None
    age: int
    sex: Sex
    weight_kg: float
    goal: Goal
    delivery_pref: str = "evening"
    backfill_days: int = 45


@dataclass
class OnboardingResult:
    profile: UserProfile
    first_insight: Insight


def onboard_user(
    db: Database,
    source: HealthSource,
    coach: Coach,
    req: OnboardingRequest,
    baseline_config: BaselineConfig = BaselineConfig(),
    triage_config: TriageConfig = TriageConfig(),
) -> OnboardingResult:
    """Persist the profile, backfill history, compute first insight.

    Idempotent: re-running with the same user_id updates the profile and
    upserts (not duplicates) metric rows.
    """
    profile = UserProfile(
        user_id=req.user_id,
        name=req.name,
        age=req.age,
        sex=req.sex,
        weight_kg=req.weight_kg,
        goal=req.goal,
        delivery_pref=req.delivery_pref,
    )
    with db.session() as s:
        repo.upsert_user(s, profile)

    today = date.today()
    start = today - timedelta(days=req.backfill_days - 1)
    ingest_range(db, source, req.user_id, start, today)

    with db.session() as s:
        all_days = repo.get_metrics_range(s, req.user_id, start, today)

    cold_start = len(all_days) < baseline_config.min_history_days
    deviations = compute_deviations(all_days, profile=profile, config=baseline_config)

    triage_out = triage(deviations, profile=profile, config=triage_config)

    today_metrics = all_days[-1] if all_days else None
    today_summary = today_metrics.summary() if today_metrics else "No data yet."

    insight = coach.generate_insight(
        profile,
        triage_out.route,
        triage_out.deviations,
        today_summary=today_summary,
        date=today,
        cold_start=cold_start,
    )

    with db.session() as s:
        repo.save_insight(s, insight)

    return OnboardingResult(profile=profile, first_insight=insight)
