"""Tests for the memory system: four stores, facade aggregation, retention
policy, and per-zone clearing.
"""

import pytest
from agent.memory import Memory
from platform_contracts import ServiceError


class TestStores:
    def test_profile_set_get_render(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.profile.set("language", "Chinese")
        m.profile.set("theme", "dark")
        assert m.profile.get("language") == "Chinese"
        assert m.profile.get("nonexistent", "default") == "default"
        assert "language" in m.profile.render()
        m.profile.delete("theme")
        assert "theme" not in m.profile.all()
        m.close()

    def test_episodic_log_search_purge(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.episodic.log("consider", "user is reading the langgraph README", run_id="r1")
        m.episodic.log("tool", "read_file", run_id="r1")
        assert len(m.episodic.recent()) == 2
        assert len(m.episodic.recent(kind="tool")) == 1
        assert m.episodic.search("langgraph")[0]["run_id"] == "r1"
        # -1 puts the cutoff one day in the future, deleting everything; 0 is avoided because
        # cutoff=now races with the just-inserted ts within the same second (DELETE ts < cutoff is flaky)
        assert m.episodic.purge(older_than_days=-1) == 2
        assert m.episodic.recent() == []
        m.close()

    def test_semantic_triple_query(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.semantic.add("langgraph", "type", "Agent orchestration framework", node_id="n1")
        m.semantic.add("langgraph", "author", "LangChain")
        assert len(m.semantic.query(subject="langgraph")) == 2
        assert m.semantic.query(keyword="orchestration")[0]["node_id"] == "n1"
        assert m.semantic.query(relation="author")[0]["object"] == "LangChain"
        m.close()

    def test_semantic_purge_by_ts(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.semantic.add("langgraph", "type", "framework")
        m.semantic.add("langgraph", "author", "LangChain")
        stale_id = m.semantic.query(relation="type")[0]["id"]
        with m.semantic._lock:  # backdate one row's ts to simulate a stale fact
            m.semantic._conn.execute(
                "UPDATE facts SET ts = ts - ? WHERE id = ?", (40 * 86400, stale_id)
            )
            m.semantic._conn.commit()
        assert m.semantic.purge(30) == 1  # stale dropped, fresh kept
        assert [f["relation"] for f in m.semantic.query(subject="langgraph")] == ["author"]
        m.close()

    def test_working_bounded(self) -> None:
        m = Memory("/nonexistent-should-not-touch")  # working only; the disk is never touched
        for i in range(250):
            m.working.add("user", f"line {i}")
        assert len(m.working.recent(500)) == 200  # maxlen bounds the store
        assert m.working.recent(1)[0]["content"] == "line 249"
        m.working.clear()
        assert m.working.recent() == []


class TestFacade:
    def test_recall_aggregates_with_source(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.profile.set("interest", "langgraph")
        m.episodic.log("consider", "user imported langgraph")
        m.semantic.add("langgraph", "type", "framework")
        hits = m.recall("langgraph")
        sources = {h["from"] for h in hits}
        assert sources == {"profile", "episodic", "semantic"}
        m.close()

    def test_retention_zero_means_agent_managed(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.episodic.log("consider", "x")
        m.semantic.add("langgraph", "type", "framework")
        assert m.purge(retention_days=0) == {"episodic": 0, "semantic": 0}  # no automatic purging
        assert len(m.episodic.recent()) == 1
        assert len(m.semantic.query()) == 1
        assert m.purge(retention_days=90)["episodic"] == 0  # nothing past its retention
        m.close()

    def test_clear_single_zone_returns_only_that_zone(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.profile.set("language", "Chinese")
        m.working.add("user", "hi")
        m.working.add("assistant", "hello")
        assert m.clear("working") == {"working": 2}  # working reports the len taken before clearing
        assert m.profile.all() == {"language": "Chinese"}  # other zones untouched
        assert len(m.working) == 0
        m.close()

    def test_clear_all_empties_every_zone(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.profile.set("language", "Chinese")
        m.episodic.log("consider", "x")
        m.semantic.add("langgraph", "type", "framework")
        out = m.clear("all")
        assert out == {"profile": 1, "episodic": 1, "semantic": 1, "working": 0}
        assert m.profile.all() == {}
        assert m.profile.render() == "(暂无用户画像)"  # empty-profile summary
        assert m.episodic.recent() == []
        assert m.semantic.query() == []
        m.close()

    def test_clear_invalid_zone_rejected(self, tmp_path) -> None:
        m = Memory(tmp_path)
        with pytest.raises(ServiceError) as exc:
            m.clear("everything")
        assert exc.value.body.code == "AGENT.INVALID_INPUT"
        m.close()


class TestMultiTermRecall:
    """Multi-term scored retrieval: terms are split, OR-matched for candidates, and ranked by hit count."""

    def test_episodic_multi_term_finds_and_ranks(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.episodic.log("consider", "discussing the context compression strategy")
        m.episodic.log("tool", "read a context-related directory")
        m.episodic.log("tool", "a totally unrelated episode")
        hits = m.episodic.search("context compression")
        summaries = [h["summary"] for h in hits]
        # A message hitting both terms ranks first; single-term hits are still recalled (whole-string LIKE would miss them all)
        assert "discussing the context compression strategy" == summaries[0]
        assert "read a context-related directory" in summaries
        assert all("unrelated" not in s for s in summaries)

    def test_episodic_single_term_unchanged(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.episodic.log("consider", "user is reading the langgraph README", run_id="r1")
        assert m.episodic.search("langgraph")[0]["run_id"] == "r1"
        # LIKE metacharacters are treated literally (searching "100%" does not match "1000")
        m.episodic.log("tool", "progress 100% done")
        m.episodic.log("tool", "count 1000 items")
        assert m.episodic.search("100%")[0]["summary"] == "progress 100% done"
        m.close()

    def test_semantic_multi_term_scoring(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.semantic.add("context", "type", "compression strategy")
        m.semantic.add("unrelated", "type", "entry")
        hits = m.semantic.query(keyword="context compression")
        assert hits[0]["subject"] == "context"
        assert all(h["subject"] != "unrelated" for h in hits)
        m.close()

    def test_semantic_whitespace_only_keyword(self, tmp_path) -> None:
        """A whitespace-only keyword is neither split nor added as a condition; behavior matches an unconditional query."""
        m = Memory(tmp_path)
        m.semantic.add("a", "type", "x")
        assert len(m.semantic.query(keyword="   ")) == 1
        m.close()

    def test_recall_profile_multi_term(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.profile.set("interest", "graph and notes")
        assert m.recall("graph whatever")[0]["key"] == "interest"
        m.close()
