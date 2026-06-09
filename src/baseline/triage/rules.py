"""Triage configuration: thresholds, modifiable metrics, clinical patterns, and
the pretest-probability gate.

The escalation philosophy is conservative by design (PRD non-goal: avoid broad
screening false positives). A worrying *pattern* is necessary but not
sufficient to escalate — it must also clear a pretest-probability bar that
depends on the user's age and history. A fit 30-year-old and a 60-year-old with
cardiac history can show the same numbers and be routed differently, correctly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from baseline.domain.models import Deviation


@dataclass(frozen=True)
class TriageConfig:
    deviation_threshold: float = 2.0  # |z| at/above which a metric is "notable"
    cold_start_widen: float = 1.5  # multiply threshold when confidence is low
    escalate_threshold: float = 0.5  # pretest probability needed to escalate


# Metrics a user can move through behaviour — these route to coaching.
MODIFIABLE_METRICS = {
    "rhr",
    "hrv",
    "sleep_mins",
    "steps",
    "active_zone_mins",
    "calories_out",
    "resp_rate",
}


@dataclass
class ClinicalPattern:
    name: str
    deviations: list[Deviation]
    base_severity: float  # prior probability before age/history adjustment


# History flags that raise pretest probability for each pattern.
_RELEVANT_HISTORY = {
    "cardiorespiratory_strain": {
        "family_history_cardiac",
        "hypertension",
        "prior_cardiac_event",
    },
    "hypoxemia": {"copd", "asthma", "sleep_apnea"},
}


def effective_threshold(deviation: Deviation, config: TriageConfig) -> float:
    """Widen the notability bar under cold-start (low-confidence) conditions."""
    base = config.deviation_threshold
    return base * config.cold_start_widen if deviation.confidence == "low" else base


def is_notable(deviation: Deviation, config: TriageConfig) -> bool:
    return deviation.abs_z >= effective_threshold(deviation, config)


def detect_clinical_patterns(
    deviations: list[Deviation], config: TriageConfig
) -> list[ClinicalPattern]:
    """Spot the small set of v1 patterns that *could* warrant escalation."""
    by_metric = {d.metric: d for d in deviations}
    patterns: list[ClinicalPattern] = []

    rhr, hrv, spo2 = by_metric.get("rhr"), by_metric.get("hrv"), by_metric.get("spo2")

    # Sustained elevated resting HR + suppressed HRV — cardio-respiratory strain.
    if (
        rhr
        and hrv
        and rhr.direction == "above"
        and rhr.sustained
        and is_notable(rhr, config)
        and hrv.direction == "below"
        and hrv.sustained
        and is_notable(hrv, config)
    ):
        patterns.append(
            ClinicalPattern("cardiorespiratory_strain", [rhr, hrv], base_severity=0.4)
        )

    # Clinically low blood oxygen (absolute, not just relative).
    if spo2 and spo2.direction == "below" and spo2.value < 92:
        patterns.append(ClinicalPattern("hypoxemia", [spo2], base_severity=0.6))

    return patterns


def pretest_probability(pattern: ClinicalPattern, age: int, history_flags: list[str]) -> float:
    """Combine pattern severity with age and relevant history into a 0..1 prior."""
    p = pattern.base_severity
    if age >= 50:
        p += 0.2
    elif age >= 40:
        p += 0.1

    relevant = _RELEVANT_HISTORY.get(pattern.name, set())
    for flag in history_flags:
        if flag in relevant:
            p += 0.2

    return min(1.0, p)
