"""Ingestion: pull from a HealthSource, normalise, and persist.

This is deliberately thin — the source already returns the normalised
:class:`DailyMetrics` shape, so the pipeline's job is orchestration and
persistence. In production the same entry points are driven by a nightly cron
(backfill/reconciliation) and webhook subscriptions (freshness); here they are
called directly.
"""

from __future__ import annotations

from datetime import date as Date

from baseline.sources.base import HealthSource
from baseline.storage import repository as repo
from baseline.storage.db import Database


def ingest_day(db: Database, source: HealthSource, user_id: str, day: Date) -> int:
    """Fetch and persist one day. Returns the number of days written (0 or 1)."""
    metrics = source.fetch_day(user_id, day)
    with db.session() as s:
        repo.save_daily_metrics(s, user_id, metrics)
    return 1


def ingest_range(
    db: Database, source: HealthSource, user_id: str, start: Date, end: Date
) -> int:
    """Fetch and persist every day in ``[start, end]``. Returns days written."""
    days = source.fetch_range(user_id, start, end)
    with db.session() as s:
        for metrics in days:
            repo.save_daily_metrics(s, user_id, metrics)
    return len(days)
