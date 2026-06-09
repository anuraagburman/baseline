"""Triage engine: route a day's deviations to monitor / coach / escalate.

Priority is escalate > coach > monitor. Escalation is gated: a clinical pattern
must also clear the pretest-probability bar (see :mod:`baseline.triage.rules`),
otherwise it is coached calmly rather than alarmed about.
"""

from __future__ import annotations

from baseline.domain.models import Deviation, TriageOutcome, TriageRoute, UserProfile
from baseline.triage.rules import (
    TriageConfig,
    detect_clinical_patterns,
    is_notable,
    pretest_probability,
)


def triage(
    deviations: list[Deviation],
    *,
    profile: UserProfile,
    config: TriageConfig = TriageConfig(),
) -> TriageOutcome:
    patterns = detect_clinical_patterns(deviations, config)

    # 1) Escalation — only if a pattern clears the pretest-probability bar.
    best_prob: float | None = None
    escalating_pattern = None
    for pattern in patterns:
        prob = pretest_probability(pattern, profile.age, profile.history_flags)
        if best_prob is None or prob > best_prob:
            best_prob = prob
        if prob >= config.escalate_threshold:
            escalating_pattern = pattern

    if escalating_pattern is not None:
        return TriageOutcome(
            route=TriageRoute.ESCALATE,
            deviations=escalating_pattern.deviations,
            rationale=(
                f"Pattern '{escalating_pattern.name}' with elevated pretest "
                f"probability ({best_prob:.2f}); worth discussing with a doctor."
            ),
            pretest_probability=best_prob,
        )

    # 2) Coaching — any notable, modifiable deviation.
    notable = sorted(
        (d for d in deviations if is_notable(d, config)),
        key=lambda d: d.abs_z,
        reverse=True,
    )
    if notable:
        return TriageOutcome(
            route=TriageRoute.COACH,
            deviations=notable,
            rationale="Notable deviation(s) from personal baseline; coachable.",
            pretest_probability=best_prob,
        )

    # 3) Monitor — nothing stands out today.
    strongest = max(deviations, key=lambda d: d.abs_z, default=None)
    return TriageOutcome(
        route=TriageRoute.MONITOR,
        deviations=[strongest] if strongest else [],
        rationale="All metrics within the user's normal range.",
        pretest_probability=best_prob,
    )
