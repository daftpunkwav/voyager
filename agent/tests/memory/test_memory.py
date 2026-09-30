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

    def test_unknown_attribute_raises(self, tmp_path) -> None:
        m = Memory(tmp_path)
        with pytest.raises(AttributeError):
            m.no_such_store  # noqa: B018 (attribute access is the assertion)


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


class TestSemanticSupersede:
    def test_supersede_replaces_same_subject_relation_from_same_source(self, tmp_path) -> None:
        mem = Memory(tmp_path / "m")
        try:
            mem.semantic.add("编辑器", "使用版本", "v1", source="distill")
            mem.semantic.add("编辑器", "使用版本", "v2", source="distill", supersede=True)
            facts = mem.semantic.query(subject="编辑器", relation="使用版本")
            assert [f["object"] for f in facts] == ["v2"]  # the stale value is gone
            # the exact-triple dedup (has_fact) is the distiller's guard, not add()'s
            assert mem.semantic.has_fact("编辑器", "使用版本", "v2") is True
        finally:
            mem.close()

    def test_supersede_never_touches_other_sources(self, tmp_path) -> None:
        mem = Memory(tmp_path / "m")
        try:
            mem.semantic.add("编辑器", "使用版本", "v1", source="feedback")
            mem.semantic.add("编辑器", "使用版本", "v2", source="distill", supersede=True)
            facts = mem.semantic.query(subject="编辑器", relation="使用版本")
            assert {f["object"] for f in facts} == {"v1", "v2"}  # both survive
        finally:
            mem.close()


class TestRecallPerSourceCap:
    """recall caps each lexical source at `limit` before the overall cap
    truncates: one zone (an ever-growing profile) cannot squeeze the others
    out of the recall budget."""

    def test_profile_hits_cannot_squeeze_episodic_out(self, tmp_path) -> None:
        m = Memory(tmp_path)
        for i in range(4):
            m.profile.set(f"topic{i}", "langgraph 笔记")
        m.episodic.log("consider", "读了 langgraph 源码")
        # limit=2 -> per-source profile cap 2, overall cap 4: both episodic
        # slots survive instead of the old all-profile wall
        hits = m.recall("langgraph", 2)
        sources = [h["from"] for h in hits]
        assert sources.count("profile") == 2  # capped per source
        assert "episodic" in sources  # not squeezed out by the profile zone
        m.close()

    def test_exclude_frees_slots_before_truncation(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.profile.set("p1", "langgraph 一")
        m.profile.set("p2", "langgraph 二")
        m.profile.set("p3", "langgraph 三")
        m.episodic.log("consider", "读了 langgraph 源码")
        hits = m.recall("langgraph", 2, exclude_profile_keys={"p1", "p2", "p3"})
        assert [h["from"] for h in hits] == ["episodic"]  # excluded profile frees the budget
        assert all(h.get("key") not in {"p1", "p2", "p3"} for h in hits if h["from"] == "profile")
        m.close()

    def test_exclude_summaries_drops_resident_card_duplicates(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.episodic.log("tool", "grep 周报")
        hits = m.recall("周报", 4, exclude_summaries={"grep 周报"})
        assert hits == []  # the entry rides a resident card, recall skips it
        m.close()

    def test_excluded_summaries_do_not_consume_episodic_slots(self, tmp_path) -> None:
        """The episodic channel oversizes its search by the exclusion set and
        truncates after the filter: resident-layer duplicates dropped from the
        first `limit` rows must not under-fill the channel — a fresh episode
        beyond the truncation point still gets its slot."""
        m = Memory(tmp_path)
        m.episodic.log("tool", "grep 周报 旧")  # rides a resident card
        m.episodic.log("tool", "grep 周报 新")  # recall-worthy, older id ranks lower
        hits = m.recall("周报", 1, exclude_summaries={"grep 周报 旧"})
        assert [h["summary"] for h in hits if h["from"] == "episodic"] == ["grep 周报 新"]
        m.close()


class TestRenderedKeys:
    """rendered_keys mirrors render()'s character cap: only keys whose lines
    render whole count as resident-layer visible (a cut line keeps its recall
    eligibility, otherwise the value would be visible nowhere)."""

    def test_keys_past_the_cap_are_not_rendered(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.profile.set("key1", "短值")
        m.profile.set("key2长名字", "非常长的值" * 10)
        text = m.profile.render(max_chars=40)
        assert text.endswith("…")  # the cap really cut something
        keys = m.profile.rendered_keys(max_chars=40)
        assert "key1" in keys
        assert "key2长名字" not in keys
        m.close()

    def test_fitting_profile_renders_every_key(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.profile.set("a", "1")
        m.profile.set("b", "2")
        assert m.profile.rendered_keys(max_chars=800) == {"a", "b"}
        assert m.profile.rendered_keys(max_chars=0) == set()  # layer off
        m.close()


class TestCorruptRows:
    """One corrupt row (disk damage / hand edit) degrades to raw text instead
    of killing the whole read path."""

    def test_corrupt_episodic_detail_degrades_to_raw(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.episodic.log("tool", "好的那行", {"action": {"tool": "grep"}})
        with m.episodic._lock:  # corrupt one row directly in the store
            m.episodic._conn.execute(
                "UPDATE episodes SET detail = '{not json' WHERE summary = '好的那行'"
            )
            m.episodic._conn.commit()
        rows = m.episodic.recent()
        assert len(rows) == 1 and rows[0]["detail"] == {"raw": "{not json"}
        assert m.episodic.search("好的那行")[0]["summary"] == "好的那行"
        m.close()

    def test_non_dict_json_detail_wraps(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.episodic.log("tool", "标量行")
        with m.episodic._lock:
            m.episodic._conn.execute("UPDATE episodes SET detail = '42' WHERE summary = '标量行'")
            m.episodic._conn.commit()
        assert m.episodic.recent()[0]["detail"] == {"raw": 42}
        m.close()

    def test_corrupt_profile_value_degrades_to_raw_text(self, tmp_path) -> None:
        m = Memory(tmp_path)
        m.profile.set("好的键", "普通值")
        m.profile.set("坏键", "值")  # created via the API, then corrupted below
        with m.profile._lock:
            m.profile._conn.execute("UPDATE profile SET value = '{{oops' WHERE key = '坏键'")
            m.profile._conn.commit()
        data = m.profile.all()
        assert data["坏键"] == "{{oops"  # raw text, no exception
        assert data["好的键"] == "普通值"  # the other rows survive
        assert "坏键" in m.profile.render()
        hits = m.recall("坏键")
        assert any(h.get("key") == "坏键" for h in hits)  # recall still serves the raw value
        m.close()
