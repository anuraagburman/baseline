"""Tests for the evidence retriever (the grounding source for the coach)."""

from __future__ import annotations

from baseline.coach.retriever import Retriever, SimpleEvidenceRetriever
from baseline.domain.models import EvidenceSnippet


def test_simple_retriever_satisfies_protocol():
    assert isinstance(SimpleEvidenceRetriever(), Retriever)


def test_retrieve_returns_snippets_matching_topic():
    snippets = SimpleEvidenceRetriever().retrieve(["sleep"], k=3)
    assert snippets
    assert all(isinstance(s, EvidenceSnippet) for s in snippets)
    assert any("sleep" in s.topic for s in snippets)


def test_retrieve_respects_k_limit():
    assert len(SimpleEvidenceRetriever().retrieve(["sleep", "rhr", "protein"], k=2)) <= 2


def test_unmatched_topic_returns_empty():
    assert SimpleEvidenceRetriever().retrieve(["astrophysics"], k=3) == []


def test_every_snippet_has_a_citation():
    for s in SimpleEvidenceRetriever().retrieve(["sleep", "rhr", "hrv", "protein"], k=10):
        assert s.citation.strip()
