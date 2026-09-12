"""Memory tools: the agent manages its own memory through the same
capabilities the settings page calls."""

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


class TestMemoryTools:
    async def test_profile_roundtrip_and_snapshot(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            belt = _belt(app)
            await belt.call(ToolCall("1", "set_profile", {"key": "lang", "value": "zh"}))
            snap = await belt.call(ToolCall("2", "get_memory", {}))
            assert "lang" in snap and "retention_days" in snap
            await belt.call(ToolCall("3", "delete_profile", {"key": "lang"}))
            assert app.memory.profile.all() == {}
            bad = await belt.call(ToolCall("4", "set_profile", {"key": " ", "value": "x"}))
            assert bad.startswith("[工具失败]")
        finally:
            app.close()

    async def test_clear_memory_is_l2(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            app.memory.profile.set("k", "v")

            async def _deny(_p: str) -> bool:
                return False

            out = await _belt(app, confirm=_deny).call(
                ToolCall("1", "clear_memory", {"zone": "profile"})
            )
            assert out.startswith("[已取消]") and app.memory.profile.all() == {"k": "v"}
            out = await _belt(app).call(ToolCall("2", "clear_memory", {"zone": "profile"}))
            assert "cleared" in out and app.memory.profile.all() == {}
        finally:
            app.close()
