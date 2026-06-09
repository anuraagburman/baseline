"""The source-abstraction contract.

Any data provider — synthetic, Google Health, Fitbit-legacy — implements this
one Protocol. Downstream code (ingestion, analytics, coach) depends on this and
never on a vendor, so swapping providers is adding a class, not a rewrite.
"""

from __future__ import annotations

from datetime import date as Date
from typing import Protocol, runtime_checkable

from baseline.domain.models import DailyMetrics


@runtime_checkable
class HealthSource(Protocol):
    def fetch_day(self, user_id: str, day: Date) -> DailyMetrics:
        """Return one normalised day of metrics for the user."""
        ...

    def fetch_range(self, user_id: str, start: Date, end: Date) -> list[DailyMetrics]:
        """Return metrics for every day in ``[start, end]`` inclusive, oldest first."""
        ...
