"""Tests for dispatch-time capability narrowing: the read-only
flag drops every write/irreversible tool by construction (never by prompt),
composes with allowlists/presets/custom definitions, and survives
checkpoint resume without regaining write tools.
"""

import pytest
from agent.llm import FakeLLM, LLMReply, ToolCall
from agent.main import build_agent
from agent.personas import ORCHESTRATOR, resolve_persona
from agent.policy import FsPolicy, PolicyEngine
from agent.runtime.state import RunStatus
from agent.subagent import Mode, TaskBook
from agent.subagent.registry import SubagentDef
from agent.tools import AgentTool, Toolbelt, ensure_workdir, fs_tools
from platform_actor import ActorContext
from platform_contracts import LOCAL_USER


def _app(tmp_path, llm=None, **kw):
    return build_agent(
        data_dir=tmp_path / "rd",
        workspace_dir=tmp_path / "ws",
        llm=llm or FakeLLM(default="Done."),
        **kw,
    )


def _write_tools() -> dict[str, AgentTool]:
    async def nope() -> str:
        return "nope"

    def _tool(name: str, *, write: bool = False, irreversible: bool = False) -> AgentTool:
        return AgentTool(
            name=name, description=name, handler=nope, write=write, irreversible=irreversible
        )

    return {
        "read": _tool("read"),
        "write": _tool("write", write=True),
        "gone": _tool("gone", write=True, irreversible=True),
        "notes__create_note": _tool("notes__create_note", write=True),
        "notes__list_notes": _tool("notes__list_notes"),
    }


class TestTrimmedReadOnly:
    def test_write_and_irreversible_dropped(self) -> None:
        belt = Toolbelt(_write_tools(), PolicyEngine()).trimmed_read_only()
        assert belt.names() == ["notes__list_notes", "read"]

    def test_none_kept_when_all_write(self) -> None:
        belt = (
            Toolbelt(
                {k: v for k, v in _write_tools().items() if k != "read"},
                PolicyEngine(),
            )
            .trimmed(["write", "gone", "notes__create_note"])
            .trimmed_read_only()
        )
        assert belt.names() == []

    async def test_dropped_call_reports_unknown(self, tmp_path) -> None:
        root = ensure_workdir(tmp_path / "ws")
        belt = Toolbelt(
            fs_tools([root]),
            PolicyEngine(fs=FsPolicy(roots=(str(root),))),
        ).trimmed_read_only()
        out = await belt.call(ToolCall("1", "write", {"path": "a", "content": "b"}))
        assert "[未知工具]" in out


class TestDispatchReadonly:
    async def test_readonly_dispatch_has_no_write_surface(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            inst = await app.master.dispatch_task("review the code", readonly=True)
            assert "write" not in inst.toolbelt.names()
            assert inst.task.readonly is True
            out = await inst.toolbelt.call(ToolCall("1", "write", {"path": "a", "content": "b"}))
            assert "[未知工具]" in out
        finally:
            app.memory.close()

    async def test_readonly_narrows_explicit_allowlist(self, tmp_path) -> None:
        """readonly composes with (never widens) an explicit allowlist."""
        app = _app(tmp_path)
        try:
            inst = await app.master.dispatch_task(
                "review",
                allowed_tools=("read", "write"),
                readonly=True,
            )
            assert inst.toolbelt.names() == ["read"]
        finally:
            app.memory.close()

    async def test_recon_preset_carries_no_write_tools(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            preset = resolve_persona("recon")
            assert preset is not None
            inst = await app.master.dispatch_task("look around", persona="recon")
            belt_tools = {
                n: t
                for n, t in zip(
                    inst.toolbelt.names(), [inst.toolbelt._tools[n] for n in inst.toolbelt.names()]
                )
            }
            assert not any(t.write or t.irreversible for t in belt_tools.values())
        finally:
            app.memory.close()

    async def test_custom_definition_readonly(self, tmp_path) -> None:
        from platform_capability import execute

        app = _app(tmp_path)
        try:
            await execute(
                app.registry,
                "register_subagent",
                ActorContext(actor=LOCAL_USER),
                {
                    "name": "revbot",
                    "description": "review bot",
                    "allowed_tools": ["read", "write"],
                    "readonly": True,
                },
            )
            inst = await app.master.dispatch_task("review", persona="revbot")
            assert inst.toolbelt.names() == ["read"]
            assert inst.task.readonly is True
        finally:
            app.memory.close()

    def test_custom_definition_rejects_non_bool_readonly(self) -> None:
        from platform_contracts import ServiceError

        with pytest.raises(ServiceError):
            SubagentDef(name="badro", description="x", readonly="yes")  # type: ignore[arg-type]  # intentionally invalid: not bool

    async def test_spawn_tool_readonly_flag_reaches_instance(self, tmp_path, settle) -> None:
        llm = FakeLLM(
            [
                LLMReply(
                    tool_calls=(
                        ToolCall(
                            "1",
                            "spawn_subagent",
                            {
                                "goal": "review the code",
                                "persona": "recon",
                                "readonly": True,
                            },
                        ),
                    )
                ),
                LLMReply(text="dispatched"),
            ]
        )
        app = _app(tmp_path, llm)
        try:
            await app.master.handle_user_message("please review the code")
            await settle(app)
            dispatched = [i for i in app.spawner.instances.values() if i.name != "chat"]
            assert dispatched, "spawn_subagent must have dispatched an instance"
            inst = dispatched[0]
            assert inst.task.readonly is True
            assert "write" not in inst.toolbelt.names()
        finally:
            app.memory.close()

    def test_orchestrator_teaches_readonly_dispatch(self) -> None:
        assert "readonly=true" in ORCHESTRATOR.system_prompt


class TestReadonlySurvivesResume:
    async def test_revived_instance_keeps_readonly_surface(self, tmp_path) -> None:
        rd = tmp_path / "rd"
        app = _app(tmp_path)
        try:
            inst = app.spawner.spawn(
                TaskBook(goal="review", mode=Mode.REACT, readonly=True),
                persona="recon",
                name="rev",
            )
            assert "write" not in inst.toolbelt.names()
            snap = inst.build_resume_snapshot()
            assert snap.to_dict()["readonly"] is True
            state = inst.state
            state.status = RunStatus.PAUSED
            state.resume = snap.to_dict()
            app.spawner._checkpoints.save(state)
            run_id = state.run_id
        finally:
            app.close()

        app2 = build_agent(data_dir=rd, workspace_dir=tmp_path / "ws", llm=FakeLLM(default="Done."))
        try:
            revived = app2.spawner.resume_from_checkpoint(run_id)
            assert revived.task.readonly is True
            assert "write" not in revived.toolbelt.names()
            out = await revived.toolbelt.call(ToolCall("1", "write", {"path": "a", "content": "b"}))
            assert "[未知工具]" in out
        finally:
            app2.close()
