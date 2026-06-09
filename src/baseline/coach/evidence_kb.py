"""A small, curated evidence base the coach grounds its claims in.

Each snippet pairs a plain-language, behaviour-oriented statement with a
citation. The ``topic`` field is a bag of keywords used by the retriever for
matching. This is deliberately tiny in v1; the production system swaps the
:class:`~baseline.coach.retriever.SimpleEvidenceRetriever` for a vector search
over a much larger base behind the same interface.

These are general wellbeing statements, not medical advice, and never frame a
metric as a diagnosis.
"""

from __future__ import annotations

from baseline.domain.models import EvidenceSnippet

EVIDENCE: list[EvidenceSnippet] = [
    EvidenceSnippet(
        id="sleep-duration",
        topic="sleep recovery energy",
        text="Adults generally feel and perform best with roughly 7–9 hours of sleep; "
        "consistently short sleep tends to blunt next-day energy and recovery.",
        citation="Hirshkowitz et al., Sleep Health (2015) — National Sleep Foundation duration recommendations.",
    ),
    EvidenceSnippet(
        id="sleep-consistency",
        topic="sleep recovery consistency",
        text="A regular sleep and wake time supports more stable energy than total "
        "hours alone; consistency is a lever you control.",
        citation="Phillips et al., Scientific Reports (2017) — regularity and circadian health.",
    ),
    EvidenceSnippet(
        id="rhr-load",
        topic="rhr recovery load stress",
        text="A resting heart rate sitting above your own usual range often reflects "
        "incomplete recovery, accumulated training load, alcohol, or stress — usually "
        "transient and responsive to a lighter, well-rested day.",
        citation="Buchheit, Frontiers in Physiology (2014) — monitoring training status with heart-rate measures.",
    ),
    EvidenceSnippet(
        id="hrv-recovery",
        topic="hrv recovery stress sleep",
        text="Heart-rate variability tends to dip when the body is under strain or "
        "under-recovered; gentle days, good sleep, and lower alcohol typically help it "
        "return toward your baseline.",
        citation="Plews et al., Sports Medicine (2013) — HRV for training readiness.",
    ),
    EvidenceSnippet(
        id="steps-activity",
        topic="steps activity movement energy general_health",
        text="Daily movement — even accumulating steps across short walks — is one of "
        "the most reliable, low-risk levers for energy and long-term health.",
        citation="Paluch et al., Lancet Public Health (2022) — steps and mortality dose-response.",
    ),
    EvidenceSnippet(
        id="protein-satiety",
        topic="protein fat_loss satiety nutrition",
        text="Higher protein intake supports satiety and helps preserve lean mass during "
        "a calorie deficit, which is useful when the goal is fat loss.",
        citation="Leidy et al., American Journal of Clinical Nutrition (2015) — protein, appetite, and body weight.",
    ),
    EvidenceSnippet(
        id="calorie-deficit",
        topic="calorie_deficit fat_loss nutrition weight",
        text="Fat loss follows a sustained, moderate energy deficit; steady and "
        "consistent tends to outperform aggressive swings.",
        citation="Hall & Kahan, Medical Clinics of North America (2018) — energy balance and weight management.",
    ),
    EvidenceSnippet(
        id="zone2-activity",
        topic="activity active_zone_mins cardio energy fitness",
        text="Regular moderate-intensity activity (conversational effort) builds aerobic "
        "fitness and day-to-day energy with a low injury risk.",
        citation="WHO Physical Activity Guidelines (2020) — 150–300 min/week moderate activity.",
    ),
]
