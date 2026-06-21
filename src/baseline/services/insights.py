"""Daily-insight service — the single code path for computing a user's insight.

Both the ``GET /daily-insight/{uid}`` route and the proactive daily-nudge
scheduler call ``compute_daily_insight`` so the coaching logic lives in exactly
one place. Returns ``None`` when the user is unknown or has no data yet (the
caller decides how to surface that — 404 for the route, skip for the scheduler).
"""

from __future__ import annotations

from datetime import date

from baseline.analytics.baseline_engine import BaselineConfig, compute_deviations
from baseline.coach.coach import Coach
from baseline.domain.models import Insight
from baseline.storage import repository as repo
from baseline.storage.db import Database
from baseline.triage.engine import triage
from baseline.triage.rules import TriageConfig


def compute_daily_insight(
    db: Database,
    coach: Coach,
    user_id: str,
    *,
    baseline_config: BaselineConfig | None = None,
    triage_config: TriageConfig | None = None,
    persist: bool = True,
) -> Insight | None:
    baseline_config = baseline_config or BaselineConfig()
    triage_config = triage_config or TriageConfig()

    with db.session() as s:
        profile = repo.get_user(s, user_id)
    if profile is None:
        return None

    with db.session() as s:
        recent = repo.get_recent_metrics(s, user_id, 60)
    if not recent:
        return None

    series = sorted(recent, key=lambda m: m.date)
    deviations = compute_deviations(series, profile=profile, config=baseline_config)
    cold_start = len(series) < baseline_config.min_history_days
    triage_out = triage(deviations, profile=profile, config=triage_config)
    today_summary = series[-1].summary()

    insight = coach.generate_insight(
        profile,
        triage_out.route,
        triage_out.deviations,
        today_summary=today_summary,
        date=date.today(),
        cold_start=cold_start,
    )

    if persist:
        with db.session() as s:
            repo.save_insight(s, insight)

    return insight
