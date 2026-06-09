"""Evidence retrieval behind a narrow interface.

v1 ships keyword matching over the curated KB. The production
``VectorRetriever`` (pgvector over day-summary + evidence embeddings) implements
the same :class:`Retriever` protocol, so the coach never changes.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from baseline.coach.evidence_kb import EVIDENCE
from baseline.domain.models import EvidenceSnippet


@runtime_checkable
class Retriever(Protocol):
    def retrieve(self, topics: list[str], k: int = 3) -> list[EvidenceSnippet]:
        """Return up to ``k`` snippets most relevant to ``topics``."""
        ...


class SimpleEvidenceRetriever:
    def __init__(self, snippets: list[EvidenceSnippet] | None = None) -> None:
        self._snippets = snippets if snippets is not None else EVIDENCE

    def retrieve(self, topics: list[str], k: int = 3) -> list[EvidenceSnippet]:
        wanted = {t.lower() for t in topics}
        scored: list[tuple[int, EvidenceSnippet]] = []
        for snippet in self._snippets:
            keywords = set(snippet.topic.lower().split())
            overlap = len(wanted & keywords)
            if overlap:
                scored.append((overlap, snippet))
        # Highest overlap first; stable for deterministic output.
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [snippet for _, snippet in scored[:k]]
