"""Tests for the triage engine and the pretest-probability escalation gate."""

from __future__ import annotations

from baseline.domain.models import (
    Deviation,
    Goal,
    Sex,
    TriageRoute,
    UserProfile,
)
from baseline.triage.engine import triage
from baseline.triage.rules import pretest_probability, ClinicalPattern


def _dev(metric, *, z, direction, value=0.0, median=0.0, sustained=True, confidence="high"):
    return Deviation(
        metric=metric,
        value=value,
        median=median,
        z=z,
        direction=direction,
        sustained=sustained,
        confidence=confidence,
    )


def _profile(age=36, history=None):
    return UserProfile(
        user_id="u1",
        age=age,
        sex=Sex.MALE,
        weight_kg=78.0,
        goal=Goal.GENERAL_HEALTH,
        history_flags=history or [],
    )


def test_all_within_normal_routes_to_monitor():
    devs = [_dev("rhr", z=0.5, direction="above"), _dev("sleep_mins", z=-1.0, direction="below")]
    out = triage(devs, profile=_profile())
    assert out.route is TriageRoute.MONITOR


def test_notable_modifiable_deviation_routes_to_coach():
    devs = [_dev("sleep_mins", z=-2.6, direction="below", value=300, median=420)]
    out = triage(devs, profile=_profile())
    assert out.route is TriageRoute.COACH
    assert any(d.metric == "sleep_mins" for d in out.deviations)


def test_clinical_pattern_in_low_pretest_user_does_not_escalate():
    # young, no history: cardio-respiratory pattern present but pretest is low
    devs = [
        _dev("rhr", z=2.5, direction="above", value=70, median=58),
        _dev("hrv", z=-2.4, direction="below", value=40, median=65),
    ]
    out = triage(devs, profile=_profile(age=30, history=[]))
    assert out.route is not TriageRoute.ESCALATE
    assert out.route is TriageRoute.COACH
    assert out.pretest_probability is not None and out.pretest_probability < 0.5


def test_clinical_pattern_in_high_pretest_user_escalates():
    devs = [
        _dev("rhr", z=2.5, direction="above", value=70, median=58),
        _dev("hrv", z=-2.4, direction="below", value=40, median=65),
    ]
    out = triage(devs, profile=_profile(age=55, history=["family_history_cardiac"]))
    assert out.route is TriageRoute.ESCALATE
    assert out.pretest_probability >= 0.5


def test_escalate_takes_priority_over_coach():
    devs = [
        _dev("rhr", z=2.5, direction="above", value=70, median=58),
        _dev("hrv", z=-2.4, direction="below", value=40, median=65),
        _dev("sleep_mins", z=-2.6, direction="below", value=300, median=420),
    ]
    out = triage(devs, profile=_profile(age=60, history=["prior_cardiac_event"]))
    assert out.route is TriageRoute.ESCALATE


def test_cold_start_widens_threshold_so_borderline_is_monitored():
    # |z| 2.2 would normally coach, but low confidence widens the threshold
    devs = [_dev("steps", z=-2.2, direction="below", value=3000, median=8400, confidence="low")]
    out = triage(devs, profile=_profile())
    assert out.route is TriageRoute.MONITOR


def test_high_confidence_borderline_is_coached():
    devs = [_dev("steps", z=-2.2, direction="below", value=3000, median=8400, confidence="high")]
    out = triage(devs, profile=_profile())
    assert out.route is TriageRoute.COACH


def test_pretest_probability_rises_with_age_and_history():
    pattern = ClinicalPattern(name="cardiorespiratory_strain", deviations=[], base_severity=0.4)
    young = pretest_probability(pattern, age=30, history_flags=[])
    old_with_history = pretest_probability(
        pattern, age=55, history_flags=["family_history_cardiac"]
    )
    assert young < old_with_history
    assert old_with_history >= 0.5
