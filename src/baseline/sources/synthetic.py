"""A synthetic :class:`HealthSource` for building and demoing without a device.

Generates deterministic, realistic-looking wearable data. Each user gets a
stable personal baseline (seeded from the user id) with small day-to-day noise,
so the analytics engine sees a believable "normal". An optional ``anomalies``
overlay injects explicit deviations on chosen days — that is how a demo gets a
real, coachable signal (e.g. a recent run of elevated resting heart rate).
"""

from __future__ import annotations

import hashlib
import math
from datetime import date as Date
from datetime import timedelta

from baseline.domain.models import DailyMetrics, SleepStages

# Per-user baseline means and the daily noise amplitude for each metric.
# (mean, spread) — spread is the peak deterministic daily wobble.
_METRIC_PROFILE = {
    "rhr": (58.0, 3.0),
    "hrv": (65.0, 8.0),
    "sleep_mins": (420.0, 35.0),
    "spo2": (97.0, 1.0),
    "resp_rate": (14.0, 1.0),
    "steps": (8400.0, 2500.0),
    "active_zone_mins": (30.0, 15.0),
    "calories_out": (2400.0, 250.0),
}


def _hash01(*parts: str) -> float:
    """Deterministic float in [0, 1) from the given string parts."""
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


class SyntheticHealthSource:
    def __init__(
        self,
        seed: str = "baseline",
        anomalies: dict[Date, dict[str, float]] | None = None,
    ) -> None:
        self.seed = seed
        self.anomalies = anomalies or {}

    def _value(self, user_id: str, day: Date, metric: str) -> float:
        mean, spread = _METRIC_PROFILE[metric]
        # Per-user offset: shifts this user's baseline by up to ~half a spread.
        user_offset = (_hash01(self.seed, user_id, metric) - 0.5) * spread
        # Per-day wobble: smooth-ish pseudo-noise unique to the day.
        phase = _hash01(self.seed, user_id, metric, day.isoformat()) * 2 * math.pi
        wobble = math.sin(phase) * spread * 0.6
        value = mean + user_offset + wobble
        value += self.anomalies.get(day, {}).get(metric, 0.0)
        return value

    def fetch_day(self, user_id: str, day: Date) -> DailyMetrics:
        rhr = self._value(user_id, day, "rhr")
        hrv = self._value(user_id, day, "hrv")
        sleep_mins = int(round(self._value(user_id, day, "sleep_mins")))
        spo2 = min(100.0, self._value(user_id, day, "spo2"))
        resp_rate = self._value(user_id, day, "resp_rate")
        steps = int(round(self._value(user_id, day, "steps")))
        active = int(round(self._value(user_id, day, "active_zone_mins")))
        calories = self._value(user_id, day, "calories_out")

        # Split sleep into stages that sum exactly to total sleep.
        deep = int(round(sleep_mins * 0.18))
        rem = int(round(sleep_mins * 0.23))
        light = sleep_mins - deep - rem

        return DailyMetrics(
            date=day,
            rhr=round(rhr, 1),
            hrv=round(hrv, 1),
            sleep_mins=sleep_mins,
            sleep_stages=SleepStages(deep=deep, rem=rem, light=light),
            spo2=round(spo2, 1),
            resp_rate=round(resp_rate, 1),
            steps=max(0, steps),
            active_zone_mins=max(0, active),
            calories_out=round(calories, 0),
        )

    def fetch_range(self, user_id: str, start: Date, end: Date) -> list[DailyMetrics]:
        days = (end - start).days
        return [self.fetch_day(user_id, start + timedelta(days=i)) for i in range(days + 1)]
