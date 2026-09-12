"""Tests for the optional vector channel: cosine math, similarity
floor, identity dedup against lexical hits, and Memory.recall fusion with a
stub embedder.
"""

from agent.memory import Memory
from agent.memory.vector import cosine, vector_hits


class StubEmbedder:
    """Deterministic unicode-bucket vectors: shared characters raise
    similarity, so tests stay readable without a real embedding model."""

    def __init__(self) -> None:
        self.batches = 0

    def embed(self, texts) -> list[list[float]]:
        self.batches += 1
        out: list[list[float]] = []
        for t in texts:
            vec = [0.0] * 32
            for ch in str(t).lower():
                vec[ord(ch) % 32] += 1.0
            norm = sum(vec) or 1.0
            out.append([v / norm for v in vec])
        return out


def test_cosine_basics() -> None:
    assert cosine([1, 0], [1, 0]) == 1.0
    assert cosine([1, 0], [0, 1]) == 0.0
    assert cosine([0, 0], [1, 1]) == 0.0  # zero magnitude: 0.0, not NaN
    assert cosine([1, 2], [1, 2, 3]) == 0.0  # length mismatch


def test_vector_hits_floor_and_ranking() -> None:
    cands = [
        ("semantic", "semantic:1", "user likes blue color", {"from": "semantic"}),
        ("semantic", "semantic:2", "totally unrelated data", {"from": "semantic"}),
    ]
    hits = vector_hits("blue color", cands, StubEmbedder(), limit=5)
    assert hits and hits[0].identity == "semantic:1"


def test_memory_recall_fuses_vector_hits(tmp_path) -> None:
    memory = Memory(tmp_path, embedder=StubEmbedder())
    memory.semantic.add("用户", "likes", "菠萝披萨", source="test")
    memory.semantic.add("同事", "works_on", "量子物理", source="test")
    hits = memory.recall("菠萝披萨")
    assert any(h.get("object") == "菠萝披萨" for h in hits)  # lexical channel
    # vector channel surfaces the other fact even without lexical overlap
    assert any(h.get("object") == "量子物理" and "similarity" in h for h in hits)


def test_memory_recall_without_embedder_stays_lexical(tmp_path) -> None:
    memory = Memory(tmp_path)
    memory.semantic.add("用户", "likes", "菠萝披萨", source="test")
    hits = memory.recall("菠萝披萨")
    assert all("similarity" not in h for h in hits)
