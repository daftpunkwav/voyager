"""Vector channel degradation: an embedder that cannot serve keeps recall
lexical and the reason is visible through vector_status."""

from __future__ import annotations

from agent.memory import Memory
from agent.memory.vector import EmbeddingUnavailable


class _Broken:
    def embed(self, texts):
        raise EmbeddingUnavailable("no embedding model configured")


class _Fake:
    def embed(self, texts):
        # query first; make "graph" texts similar to the query
        return [[1.0, 0.0] if "graph" in t else [0.0, 1.0] for t in texts]


class TestVectorDegrade:
    def test_broken_embedder_keeps_lexical_and_reports(self, tmp_path) -> None:
        mem = Memory(tmp_path / "m", embedder=_Broken())
        mem.profile.set("topic", "graph indexing")
        hits = mem.recall("graph")
        assert any(h["from"] == "profile" for h in hits)
        status = mem.vector_status()
        assert status["enabled"] is False and "no embedding model" in status["note"]
        mem.close()

    def test_working_embedder_adds_similarity_hits(self, tmp_path) -> None:
        mem = Memory(tmp_path / "m", embedder=_Fake())
        mem.semantic.add("voyager", "uses", "graph engine", source="test")
        hits = mem.recall("graph")
        assert mem.vector_status()["enabled"] is True
        assert any("similarity" in h or h["from"] == "semantic" for h in hits)
        mem.close()

    def test_no_embedder_is_explicit(self, tmp_path) -> None:
        mem = Memory(tmp_path / "m")
        assert mem.vector_status()["enabled"] is False
        mem.close()
