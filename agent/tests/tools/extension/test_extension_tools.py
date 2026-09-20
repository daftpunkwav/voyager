"""Extension tools: plugins / MCP / user hooks read and mutate through the
same capabilities the settings page calls; mutations are L2."""

from __future__ import annotations

from agent.build import build_agent
from agent.llm import FakeLLM, ToolCall
from agent.tools import Toolbelt


def _belt(app, *, confirm=None) -> Toolbelt:
    async def _yes(_prompt: str) -> bool:
        return True

    async def _noop(_msg: str) -> None:
        return None

    root = app.spawner._toolbelt
    return Toolbelt(dict(root._tools), root._policy, confirm=confirm or _yes, notify=_noop)


class TestExtensionTools:
    async def test_read_surfaces(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            plugins_dir=tmp_path / "plugins",
        )
        try:
            belt = _belt(app)
            assert (
                '"items"'
                in await belt.call(ToolCall("1", "extension", {"kind": "plugin", "action": "list"}))
            )
            assert (
                await belt.call(ToolCall("2", "extension", {"kind": "mcp", "action": "list"}))
                == "[]"
            )
            assert (
                '"items"'
                in await belt.call(ToolCall("3", "extension", {"kind": "hook", "action": "list"}))
            )
        finally:
            app.close()

    async def test_mutations_execute_without_confirm(self, tmp_path) -> None:
        """Confirm retired: mutations run even with a deny-confirm channel;
        failures come from the handler, never from a confirm branch."""
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            plugins_dir=tmp_path / "plugins",
        )
        try:
            asked: list[str] = []

            async def _deny(prompt: str) -> bool:
                asked.append(prompt)
                return False

            belt = _belt(app, confirm=_deny)
            for args in (
                {"kind": "plugin", "action": "install", "source_dir": str(tmp_path / "ws" / "nope")},
                {"kind": "plugin", "action": "uninstall", "name": "nope"},
            ):
                out = await belt.call(ToolCall("1", "extension", args))
                assert "[已取消]" not in out and "[需确认]" not in out, args
                assert out, args  # handler-level error text for missing targets
            out = await belt.call(ToolCall("2", "extension", {"kind": "hook", "action": "reload"}))
            assert "loaded" in out
            assert asked == []
        finally:
            app.close()

    def test_escalation_boundary_tools_are_absent(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            names = set(app.spawner._toolbelt.names())
            assert not names & {
                "set_plugin_approval",
                "add_mcp_server",
                "approve_mcp_tools",
                "remove_mcp_server",
            }
        finally:
            app.close()
