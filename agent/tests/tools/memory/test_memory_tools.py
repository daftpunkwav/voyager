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
            await belt.call(
                ToolCall("1", "memory", {"action": "remember", "key": "lang", "value": "zh"})
            )
            snap = await belt.call(ToolCall("2", "memory", {"action": "query"}))
            assert "lang" in snap and "retention_days" in snap
            await belt.call(ToolCall("3", "memory", {"action": "forget", "key": "lang"}))
            assert app.memory.profile.all() == {}
            bad = await belt.call(
                ToolCall("4", "memory", {"action": "remember", "key": " ", "value": "x"})
            )
            # capability INVALID_INPUT now surfaces under the [参数错误] label
            assert bad.startswith("[参数错误]")
        finally:
            app.close()

    async def test_clear_memory_executes_without_confirm(self, tmp_path) -> None:
        """Confirm retired: the irreversible clear runs even with a
        deny-confirm channel (the permission modes are the gate now)."""
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            app.memory.profile.set("k", "v")

            async def _deny(_p: str) -> bool:
                return False

            out = await _belt(app, confirm=_deny).call(
                ToolCall("1", "memory", {"action": "clear", "zone": "profile"})
            )
            assert "cleared" in out and app.memory.profile.all() == {}
        finally:
            app.close()

    async def test_recall_limit_clamped(self, tmp_path) -> None:
        """One-shot recall stays bounded: the capability clamps limit to
        [1, 20] and degrades a wrong-type limit to the default."""
        from platform_actor import ActorContext
        from platform_capability import execute
        from platform_contracts import LOCAL_USER

        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            seen: list[int] = []

            def _recall(query: str, limit: int = 8) -> list:
                seen.append(limit)
                return []

            app.memory.recall = _recall  # type: ignore[method-assign]
            await execute(
                app.registry,
                "memory",
                ActorContext(actor=LOCAL_USER),
                {"action": "recall", "query": "x"},
            )
            await execute(
                app.registry,
                "memory",
                ActorContext(actor=LOCAL_USER),
                {"action": "recall", "query": "x", "limit": 100},
            )
            await execute(
                app.registry,
                "memory",
                ActorContext(actor=LOCAL_USER),
                {"action": "recall", "query": "x", "limit": 0},
            )
            assert seen == [8, 20, 1]
        finally:
            app.memory.close()
