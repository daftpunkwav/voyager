"""Optional vector channel for memory recall: embedding protocol,
cosine similarity, and lexical/vector score fusion.

The embedder is injected (Memory(embedder=...)); without one, recall stays
purely lexical - zero external dependencies by default. Fusion is additive:
lexical hits keep their term-count score, vector-only candidates join with
their similarity (below the threshold they are dropped), and ties still favor
recency. Implementors should cache embeddings per text; recall embeds the
whole candidate pool on every call.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

#: Vector-only candidates below this similarity are dropped (tuned so that
#: unrelated-but-shared-stopword texts never surface)
SIMILARITY_FLOOR = 0.3


class EmbeddingUnavailable(RuntimeError):
    """Raised by an embedder that cannot serve right now (unconfigured model,
    no usable provider, upstream failure); recall degrades to lexical."""


class EmbeddingFn(Protocol):
    """Batch embedding surface (sync on purpose: recall is a sync call path;
    implementors may cache or delegate to a worker thread internally)."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity; zero-magnitude vectors yield 0.0 (never NaN)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


@dataclass(frozen=True)
class VectorCandidate:
    """One recall candidate scored by the vector channel (payload matches the
    shape recall() returns for that source)."""

    source: str  # profile | episodic | semantic
    identity: str  # stable per-item id for dedup against lexical hits
    text: str
    payload: dict[str, Any]
    similarity: float


def vector_hits(
    query: str,
    candidates: list[tuple[str, str, str, dict[str, Any]]],
    embedder: EmbeddingFn,
    *,
    limit: int,
    floor: float = SIMILARITY_FLOOR,
) -> list[VectorCandidate]:
    """Embed the pool once and return similarity-ranked candidates.

    `candidates` items are (source, identity, text, payload). Entries below
    the similarity floor are dropped so an injected embedder cannot flood
    recall with weak matches.
    """
    if not candidates:
        return []
    vectors = embedder.embed([query, *(text for _, _, text, _ in candidates)])
    qvec = vectors[0]
    scored = [
        VectorCandidate(
            source=source,
            identity=identity,
            text=text,
            payload=payload,
            similarity=cosine(qvec, vectors[i + 1]),
        )
        for i, (source, identity, text, payload) in enumerate(candidates)
    ]
    scored = [c for c in scored if c.similarity >= floor]
    scored.sort(key=lambda c: -c.similarity)
    return scored[:limit]


__all__ = [
    "SIMILARITY_FLOOR",
    "EmbeddingFn",
    "EmbeddingUnavailable",
    "VectorCandidate",
    "cosine",
    "vector_hits",
]
