"""Tests for the on-demand loader: full text of skills/memory/pages is read
only when asked for, and every load is audit-logged."""

from agent.context import OnDemandLoader, PageContextRegistry
from agent.memory import Memory
from agent.skills.loader import SkillLoader


class TestOnDemandLoader:
    def test_loads_are_audited(self, tmp_path) -> None:
        d = tmp_path / "my-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("# my-skill\n\ndescription\n", encoding="utf-8")
        memory = Memory(tmp_path / "mem")
        memory.profile.set("interest", "graph")
        pages = PageContextRegistry()
        pages.update("notes", "3 notes")
        loader = OnDemandLoader(skills=SkillLoader([tmp_path]), memory=memory, pages=pages)
        assert "description" in loader.skill_text("my-skill")
        assert loader.recall("graph")[0]["from"] == "profile"
        assert "notes" in loader.page_summary()
        assert [r["kind"] for r in loader.loads] == ["skill", "memory", "page"]  # loads are audited
        memory.close()
