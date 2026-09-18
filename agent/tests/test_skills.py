"""Tests for the skill system: resident index with on-demand full text, and
confirm-gated auto-organization of repeated flows.
"""

import pytest
from agent.context import ContextBuilder
from agent.memory.episodic import EpisodicMemory
from agent.skills.loader import SkillLoader
from agent.skills.organizer import SkillOrganizer


def _make_skill(root, name: str, desc: str) -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"# {name}\n\n{desc}\n\n## Steps\n1. …\n", encoding="utf-8")


class TestLoader:
    def test_index_resident_full_on_demand(self, tmp_path) -> None:
        _make_skill(tmp_path, "explore-repo", "explore the repo structure")
        _make_skill(tmp_path, "summarize", "summarize material")
        loader = SkillLoader([tmp_path, tmp_path / "nonexistent-dir"])
        index = loader.index()
        assert [i["name"] for i in index] == ["explore-repo", "summarize"]
        assert index[0]["description"] == "explore-repo"  # first heading line
        assert "explore the repo structure" in loader.full_text("explore-repo")

    def test_unknown_skill_raises(self, tmp_path) -> None:
        with pytest.raises(KeyError, match="unknown skill"):
            SkillLoader([tmp_path]).full_text("nope")

    def test_bad_file_skipped_not_fatal(self, tmp_path, caplog) -> None:
        """A bad SKILL.md (non-UTF-8) is skipped with a warning and never breaks the index —
        the index feeds context building every turn, so one bad file must not take the agent down."""
        _make_skill(tmp_path, "good-one", "a normal skill")
        bad_dir = tmp_path / "bad-one"
        bad_dir.mkdir()
        (bad_dir / "SKILL.md").write_bytes(b"\xff\xfe#\xff\xfe bad bytes")
        loader = SkillLoader([tmp_path])
        assert [i["name"] for i in loader.index()] == ["good-one"]
        assert any("unreadable" in r.message for r in caplog.records)
        with pytest.raises(KeyError, match="unknown skill"):
            loader.full_text("bad-one")  # absent from the index, same as unknown


class TestIndexVisibility:
    """The index enters the context, leaks no local paths, and plugin examples stay out of the default index."""

    def test_index_entries_have_no_path(self, tmp_path) -> None:
        _make_skill(tmp_path, "my-skill", "do one thing")
        for entry in SkillLoader([tmp_path]).index():
            assert set(entry) == {"name", "description"}  # path never leaves the loader

    def test_builder_injects_skill_layer(self, tmp_path) -> None:
        # _read_desc uses the first heading line as the description, matching real skill files
        d = tmp_path / "explore-repo"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "# explore repo structure\n\nThe flow for understanding a repo:…\n", encoding="utf-8"
        )
        builder = ContextBuilder(skills=SkillLoader([tmp_path]))
        system = builder.system()
        assert "【可用 skill】" in system
        assert "explore-repo: explore repo structure" in system
        assert "load_skill" in system  # points at fetching full text on demand
        assert str(tmp_path) not in system  # no local absolute paths leak

    def test_builder_omits_layer_when_no_skills(self, tmp_path) -> None:
        builder = ContextBuilder(skills=SkillLoader([tmp_path / "empty"]))
        assert "【可用 skill】" not in builder.system()


class TestDefaultWiring:
    """build_agent default roots: built-in plus the user skills directory; plugin _example stays out."""

    def _build(self, tmp_path):
        from agent.llm import FakeLLM
        from agent.main import build_agent

        return build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())

    def test_builtin_in_user_example_out(self, tmp_path) -> None:
        app = self._build(tmp_path)
        try:
            names = [e["name"] for e in app.skills.index()]
            assert "explore-repo" in names  # built-in skill indexed
            assert "daily-note" not in names  # unapproved plugins/_example never enters the index
        finally:
            app.memory.close()

    def test_user_skill_dir_discovered(self, tmp_path) -> None:
        d = tmp_path / "ws" / "skills" / "my-workflow"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("# my-workflow\n\nthree-step wrap-up flow\n", encoding="utf-8")
        app = self._build(tmp_path)
        try:
            assert "my-workflow" in [e["name"] for e in app.skills.index()]
        finally:
            app.memory.close()

    async def test_spawned_system_contains_skill_index(self, tmp_path) -> None:
        from agent.subagent import Mode, TaskBook

        app = self._build(tmp_path)
        try:
            inst = app.spawner.spawn(TaskBook(goal="test", mode=Mode.REACT), persona="orchestrator")
            assert "【可用 skill】" in inst.system_prompt
            assert "explore-repo: explore-repo(skill 内置示例)" in inst.system_prompt
        finally:
            app.memory.close()


class TestSkillsWriteGuard:
    """Integration: toolbelt writes into skills are refused by policy, so a fake skill never enters the index."""

    async def test_write_file_rejected_and_not_indexed(self, tmp_path) -> None:
        from agent.llm import FakeLLM, ToolCall
        from agent.main import build_agent

        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            belt = app.spawner._toolbelt
            out = await belt.call(
                ToolCall("1", "write_file", {"path": "skills/pwn/SKILL.md", "content": "injection"})
            )
            assert "[已拒绝]" in out
            assert not (tmp_path / "ws" / "skills" / "pwn").exists()
            assert "pwn" not in [e["name"] for e in app.skills.index()]
        finally:
            app.memory.close()


class TestOrganizer:
    def _fill(self, db, runs: int = 3) -> EpisodicMemory:
        ep = EpisodicMemory(db)
        for i in range(runs):
            ep.log("tool", "read_file", run_id=f"r{i}")
            ep.log("tool", "write_file", run_id=f"r{i}")
        return ep

    def test_detect_repeated_sequence(self, tmp_path) -> None:
        ep = self._fill(tmp_path / "ep.db")
        org = SkillOrganizer(ep)
        hits = ep and org.detect(min_count=3, seq_len=2)
        assert hits == [{"sequence": ["read_file", "write_file"], "count": 3}]
        assert org.detect(min_count=4) == []  # below the threshold, nothing reported

    async def test_propose_publishes_event_without_writing(self, tmp_path) -> None:
        ep = self._fill(tmp_path / "ep.db")
        published: list[dict] = []

        async def emit(type_: str, **payload) -> None:
            published.append({"type": type_, **payload})

        org = SkillOrganizer(ep, emit=emit)
        proposed = await org.propose(min_count=3)
        assert len(published) == 1
        assert published[0]["type"] == "skill.proposed"
        assert published[0]["sequence"] == ["read_file", "write_file"]
        assert proposed[0]["count"] == 3
        assert not (tmp_path / "skills").exists()  # saving is propose_skill's job

    async def test_no_emit_channel_proposes_nothing(self, tmp_path) -> None:
        ep = self._fill(tmp_path / "ep.db")

        org = SkillOrganizer(ep)
        assert await org.propose(min_count=3) == []
        assert not (tmp_path / "skills").exists()
