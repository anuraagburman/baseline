"""Personal-baseline / deviation engine.

For each metric we ask: *how far is today from this user's own normal?* The
answer is a robust z-score against a rolling window of the user's recent days,
using the median and MAD (median absolute deviation) so a single odd day does
not distort the baseline. Recent persistence is distinguished from one-off
spikes, and when there is too little personal history we fall back to
population norms and flag low confidence (cold start).

This is intentionally provider-agnostic and stateless: feed it a series of
:class:`DailyMetrics`, get back :class:`Deviation` objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median, pstdev

from baseline.domain.models import DailyMetrics, Deviation, Direction, UserProfile

# Multiplier that makes a MAD-based z comparable to a standard z for normal data
# (1 / 1.4826 ≈ 0.6745).
_ROBUST_K = 0.6745

# The numeric metrics we evaluate, with how to read each off a DailyMetrics.
_METRIC_GETTERS = {
    "rhr": lambda m: float(m.rhr),
    "hrv": lambda m: float(m.hrv),
    "sleep_mins": lambda m: float(m.sleep_mins),
    "spo2": lambda m: float(m.spo2),
    "resp_rate": lambda m: float(m.resp_rate),
    "steps": lambda m: float(m.steps),
    "active_zone_mins": lambda m: float(m.active_zone_mins),
    "calories_out": lambda m: float(m.calories_out),
}

# Population norms (median, std) by sex band — the cold-start fallback when the
# user has too little personal history. Coarse on purpose.
_POP_NORMS: dict[str, dict[str, tuple[float, float]]] = {
    "rhr": {"male": (60.0, 9.0), "female": (63.0, 9.0), "other": (62.0, 9.0)},
    "hrv": {"male": (55.0, 18.0), "female": (52.0, 18.0), "other": (53.0, 18.0)},
    "sleep_mins": {"male": (420.0, 60.0), "female": (430.0, 60.0), "other": (425.0, 60.0)},
    "spo2": {"male": (97.0, 1.5), "female": (97.0, 1.5), "other": (97.0, 1.5)},
    "resp_rate": {"male": (14.0, 2.0), "female": (15.0, 2.0), "other": (14.5, 2.0)},
    "steps": {"male": (7500.0, 3000.0), "female": (7500.0, 3000.0), "other": (7500.0, 3000.0)},
    "active_zone_mins": {"male": (25.0, 15.0), "female": (25.0, 15.0), "other": (25.0, 15.0)},
    "calories_out": {"male": (2500.0, 350.0), "female": (2100.0, 350.0), "other": (2300.0, 350.0)},
}


@dataclass(frozen=True)
class BaselineConfig:
    window_days: int = 28
    min_history_days: int = 14  # below this -> cold start (low confidence)
    sustain_window: int = 3  # recent days inspected for persistence
    sustain_threshold: float = 1.5  # |z| a recent day must exceed to "count"
    sustain_min_count: int = 2  # how many recent days must count to be sustained


def _direction(value: float, center: float) -> Direction:
    if value > center:
        return "above"
    if value < center:
        return "below"
    return "normal"


def _robust_z(value: float, center: float, mad: float, fallback_std: float) -> float:
    """MAD-based z, falling back to std when MAD is zero (e.g. ties)."""
    if mad > 0:
        return _ROBUST_K * (value - center) / mad
    if fallback_std > 0:
        return (value - center) / fallback_std
    return 0.0


def _baseline_for_metric(
    history_values: list[float],
    today: float,
    metric: str,
    profile: UserProfile | None,
    config: BaselineConfig,
) -> tuple[float, float, float]:
    """Return (center, mad, fallback_std) for the metric.

    Uses the personal window when there is enough history; otherwise population
    norms (if a profile is available) so cold-start days still get a signal.
    """
    enough_history = len(history_values) >= config.min_history_days
    if enough_history or (not enough_history and profile is None and history_values):
        center = median(history_values)
        deviations = [abs(v - center) for v in history_values]
        mad = median(deviations) if deviations else 0.0
        fallback_std = pstdev(history_values) if len(history_values) > 1 else 0.0
        return center, mad, fallback_std

    # Cold start with a known profile -> population norms.
    if profile is not None:
        center, std = _POP_NORMS[metric][profile.sex.value]
        return center, 0.0, std

    # No history and no profile: nothing to compare against.
    return today, 0.0, 0.0


def compute_deviations(
    series: list[DailyMetrics],
    *,
    profile: UserProfile | None = None,
    config: BaselineConfig = BaselineConfig(),
) -> list[Deviation]:
    """Evaluate the last day in ``series`` against the preceding window.

    ``series`` must be ordered oldest -> newest. Returns one Deviation per
    numeric metric.
    """
    if not series:
        return []

    today = series[-1]
    window = series[:-1][-config.window_days:]
    confidence = "high" if len(window) >= config.min_history_days else "low"

    deviations: list[Deviation] = []
    for metric, getter in _METRIC_GETTERS.items():
        today_val = getter(today)
        history_values = [getter(m) for m in window]
        center, mad, fallback_std = _baseline_for_metric(
            history_values, today_val, metric, profile, config
        )

        z = _robust_z(today_val, center, mad, fallback_std)
        sustained = _is_sustained(series, getter, center, mad, fallback_std, z, config)

        deviations.append(
            Deviation(
                metric=metric,
                value=round(today_val, 2),
                median=round(center, 2),
                z=round(z, 4),
                direction=_direction(today_val, center),
                sustained=sustained,
                confidence=confidence,
            )
        )
    return deviations


def _is_sustained(
    series: list[DailyMetrics],
    getter,
    center: float,
    mad: float,
    fallback_std: float,
    today_z: float,
    config: BaselineConfig,
) -> bool:
    """A deviation is *sustained* when several recent days deviate the same way.

    Distinguishes a meaningful trend from a one-off spike, so the coach can
    weight it accordingly (and avoid over-reacting to noise).
    """
    if today_z == 0:
        return False
    recent = series[-config.sustain_window:]
    sign = 1 if today_z > 0 else -1
    count = 0
    for m in recent:
        z = _robust_z(getter(m), center, mad, fallback_std)
        if z * sign >= config.sustain_threshold:
            count += 1
    return count >= config.sustain_min_count
