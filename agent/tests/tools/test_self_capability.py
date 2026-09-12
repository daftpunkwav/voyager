"""self_capability: binding an agent capability as a tool runs the same
guard chain as the human path, audited as actor=agent; guards short-circuit.
"""

from __future__ import annotations

from agent.build import build_agent
from agent.llm import FakeLLM, ToolCall
from agent.tools import Toolbelt
from agent.tools.core.self_capability import capability_tool
from platform_capability import InMemoryAuditSink


def _belt(app, tools, *, confirm=None, notify=None) -> Toolbelt:
    async def _yes(_prompt: str) -> bool:
        return True

    async def _noop(_msg: str) -> None:
        return None

    return Toolbelt(
        tools, app.spawner._toolbelt._policy, confirm=confirm or _yes, notify=notify or _noop
    )


class TestCapabilityTool:
    async def test_executes_as_agent_actor_and_audits(self, tmp_path) -> None:
        sink = InMemoryAuditSink()
        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM(), audit=[sink]
        )
        try:
            tool = capability_tool(
                app.registry, "set_profile", description="x", audit=[sink], write=True
            )
            belt = _belt(app, {tool.name: tool})
            out = await belt.call(ToolCall("1", "set_profile", {"key": "lang", "value": "zh"}))
            assert "ok" in out
            assert app.memory.profile.all() == {"lang": "zh"}
            entries = [e for e in sink.entries if e.capability == "set_profile"]
            assert entries and entries[-1].actor_kind == "agent" and entries[-1].ok is True
        finally:
            app.close()

    async def test_schema_is_derived_from_the_capability(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            tool = capability_tool(app.registry, "rename_session", description="x")
            assert set(tool.schema["properties"]) == {"session_id", "title"}
            assert tool.schema.get("required") == ["session_id", "title"]
        finally:
            app.close()

    async def test_guard_refusal_never_reaches_the_capability(self, tmp_path) -> None:
        sink = InMemoryAuditSink()
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            tool = capability_tool(
                app.registry,
                "set_profile",
                description="x",
                audit=[sink],
                write=True,
                guard=lambda args: "[已拒绝] nope" if args.get("key") == "blocked" else None,
            )
            belt = _belt(app, {tool.name: tool})
            out = await belt.call(ToolCall("1", "set_profile", {"key": "blocked", "value": "v"}))
            assert out.startswith("[已拒绝]")
            assert app.memory.profile.all() == {}
            assert sink.entries == []
        finally:
            app.close()

    async def test_irreversible_goes_through_l2_confirm(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            asked: list[str] = []

            async def _deny(prompt: str) -> bool:
                asked.append(prompt)
                return False

            tool = capability_tool(
                app.registry, "clear_memory", description="x", write=True, irreversible=True
            )
            belt = _belt(app, {tool.name: tool}, confirm=_deny)
            app.memory.profile.set("k", "v")
            out = await belt.call(ToolCall("1", "clear_memory", {"zone": "profile"}))
            assert out.startswith("[已取消]")
            assert asked and app.memory.profile.all() == {"k": "v"}
        finally:
            app.close()
