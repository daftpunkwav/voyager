"""Tests for the assembly-time tool registry: source ordering,
clash resolution, origin tracking, and assembly roster parity.
"""

import pytest
from agent.llm import FakeLLM
from agent.main import build_agent
from agent.tools import AgentTool, StaticToolSource, ToolRegistry


def _tool(name: str) -> AgentTool:
    async def handler() -> str:
        return name

    return AgentTool(name=name, description=f"{name} tool", handler=handler)


class TestToolRegistry:
    def test_build_merges_in_registration_order(self) -> None:
        reg = ToolRegistry()
        reg.add(StaticToolSource("first", {"a": _tool("a")}))
        reg.add(StaticToolSource("second", {"b": _tool("b")}))
        built = reg.build()
        assert set(built) == {"a", "b"}
        assert reg.source_names() == ("first", "second")

    def test_later_source_wins_name_clash(self) -> None:
        reg = ToolRegistry()
        reg.add(StaticToolSource("builtin", {"x": _tool("x-old")}))
        reg.add(StaticToolSource("domain", {"x": _tool("x-new")}))
        built = reg.build()
        assert built["x"].description == "x-new tool"
        assert reg.origins() == {"x": "domain"}

    def test_origins_track_every_name(self) -> None:
        reg = ToolRegistry()
        reg.add(StaticToolSource("fs", {"read_file": _tool("read_file")}))
        reg.add(StaticToolSource("shell", {"run_shell": _tool("run_shell")}))
        assert reg.origins() == {"read_file": "fs", "run_shell": "shell"}

    def test_duplicate_source_name_rejected(self) -> None:
        reg = ToolRegistry()
        reg.add(StaticToolSource("fs", {}))
        with pytest.raises(ValueError):
            reg.add(StaticToolSource("fs", {}))

    def test_empty_source_name_rejected(self) -> None:
        with pytest.raises(ValueError):
            StaticToolSource("", {})

    def test_build_returns_independent_dict(self) -> None:
        reg = ToolRegistry()
        reg.add(StaticToolSource("fs", {"a": _tool("a")}))
        built = reg.build()
        built.pop("a")
        assert set(reg.build()) == {"a"}

    def test_core_tools_exact_set(self) -> None:
        """The always-active builtin surface is explicit: adding a tool here
        spends first-round schema budget, so growth is a deliberate diff."""
        from agent.tools.core.activate import CORE_TOOLS

        assert set(CORE_TOOLS) == {
            "ask_user",
            "spawn_subagent",
            "skill",
            "memory",
            "request_context",
            "todowrite",
            "read",
            "write",
            "edit",
            "bash",
            "grep",
            "glob",
            "settings__get_theme",
            "settings__set_theme",
            "activate_tools",
            "context",
            "session",
            "llm__get_usage_stats",
        }


class TestAssemblyRosterParity:
    def test_builtin_roster_names_unchanged(self, tmp_path, caplog) -> None:
        """Assembly through the registry yields the exact builtin roster, and
        the startup log reports per-source counts (origins() is consumed)."""
        import logging

        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            assert set(app.spawner._toolbelt.names()) == {
                "abandon_resumable_checkpoint",
                "ask_user",
                "bash",
                "cancel_run",
                "context",
                "delete_subagent",
                "edit",
                "extension",
                "glob",
                "goal_read",
                "goal_write",
                "grep",
                "jobs",
                "list_resumable_checkpoints",
                "list_subagents",
                "memory",
                "observe",
                "pause_run",
                "plan",
                "reach_out",
                "read",
                "read_board",
                "register_subagent",
                "request_context",
                "resume_run",
                "scratchpad",
                "session",
                "skill",
                "spawn_subagent",
                "todowrite",
                "tools",
                "wait_subagent",
                "web_fetch",
                "web_search",
                "write",
                "write_board",
            }
            with caplog.at_level(logging.INFO, logger="agent.main"):
                build_agent(
                    data_dir=tmp_path / "rd2",
                    workspace_dir=tmp_path / "ws2",
                    llm=FakeLLM(),
                ).close()
            assert "tool roster:" in caplog.text and "fs(" in caplog.text
        finally:
            app.close()
