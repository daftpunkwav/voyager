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


def _notes_tools() -> dict[str, AgentTool]:
    """Bridge-domain stand for prefix-grant tests: notes__create/list only."""
    return {k: v for k, v in _write_tools().items() if k.startswith("notes__")}


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
                "subagent",
                ActorContext(actor=LOCAL_USER),
                {
                    "action": "register",
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
                            "subagent",
                            {
                                "action": "spawn",
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
            assert dispatched, "subagent(action=spawn) must have dispatched an instance"
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


class TestSurfaceInheritance:
    """Assignment-time surface intersection: a dispatch from inside a live
    instance can narrow but never widen past the dispatcher's own surface;
    explicit out-of-surface entries are rejected with a readable error."""

    async def _dispatch_under(self, app, parent, **kw):
        from agent.runtime.current import current_instance

        token = current_instance.set(parent)
        try:
            return await app.master.dispatch_task(**kw)
        finally:
            current_instance.reset(token)

    async def test_implicit_inherit_is_exact(self, tmp_path) -> None:
        """allowed_tools omitted: the child inherits exactly the parent surface."""
        app = _app(tmp_path)
        try:
            parent = app.spawner.spawn(
                TaskBook(goal="parent", allowed_tools=("read", "grep", "glob")), name="parent"
            )
            child = await self._dispatch_under(app, parent, goal="child task")
            assert set(child.toolbelt.names()) == {"glob", "grep", "read"}
        finally:
            app.close()

    async def test_explicit_list_narrows_within_parent(self, tmp_path) -> None:
        """An in-surface allowlist intersects down to exactly those tools."""
        app = _app(tmp_path)
        try:
            parent = app.spawner.spawn(
                TaskBook(goal="parent", allowed_tools=("read", "grep", "glob")), name="parent"
            )
            child = await self._dispatch_under(
                app, parent, goal="narrower", allowed_tools=("read", "grep")
            )
            assert set(child.toolbelt.names()) == {"grep", "read"}
        finally:
            app.close()

    async def test_out_of_surface_request_rejects_with_names(self, tmp_path) -> None:
        from platform_contracts import ServiceError

        app = _app(tmp_path)
        try:
            parent = app.spawner.spawn(
                TaskBook(goal="parent", allowed_tools=("read", "grep")), name="parent"
            )
            with pytest.raises(ServiceError) as exc:
                await self._dispatch_under(
                    app, parent, goal="widening", allowed_tools=("read", "write")
                )
            assert "write" in str(exc.value)
            assert exc.value.body.code == "AGENT.FORBIDDEN"
        finally:
            app.close()

    async def test_prefix_entry_partial_availability_intersects(self, tmp_path) -> None:
        """A prefix grant resolves against the parent surface, not the root."""
        notes = _notes_tools()
        app = _app(tmp_path, extra_tools=notes)
        try:
            parent = app.spawner.spawn(
                TaskBook(goal="parent", allowed_tools=("read", "notes__*")), name="parent"
            )
            child = await self._dispatch_under(
                app, parent, goal="bridged", allowed_tools=("notes__*",)
            )
            assert set(child.toolbelt.names()) == set(notes)
        finally:
            app.close()

    async def test_grandchild_chain_stays_monotone(self, tmp_path) -> None:
        """Each link intersects with its own (already narrowed) surface."""
        app = _app(tmp_path)
        try:
            parent = app.spawner.spawn(
                TaskBook(goal="parent", allowed_tools=("read", "grep", "glob")), name="parent"
            )
            child = await self._dispatch_under(
                app, parent, goal="child", allowed_tools=("read", "grep")
            )
            grandchild = await self._dispatch_under(
                app, child, goal="grandchild", allowed_tools=("read",)
            )
            assert set(grandchild.toolbelt.names()) == {"read"}
        finally:
            app.close()

    async def test_grandchild_out_of_chain_request_rejects(self, tmp_path) -> None:
        from platform_contracts import ServiceError

        app = _app(tmp_path)
        try:
            parent = app.spawner.spawn(
                TaskBook(goal="parent", allowed_tools=("read", "grep", "glob")), name="parent"
            )
            child = await self._dispatch_under(app, parent, goal="child")
            with pytest.raises(ServiceError) as exc:
                await self._dispatch_under(
                    app, child, goal="grandchild", allowed_tools=("read", "write")
                )
            assert "write" in str(exc.value)
        finally:
            app.close()

    async def test_top_level_dispatch_keeps_full_surface(self, tmp_path) -> None:
        """No live parent (queue/goal driver path): the root roster applies, unchanged."""
        app = _app(tmp_path)
        try:
            inst = await app.master.dispatch_task("top level task")
            assert "write" in inst.toolbelt.names()
        finally:
            app.close()

    async def test_preset_enumerating_unmounted_domain_intersects_silently(self, tmp_path) -> None:
        """Curated persona allowlists (recon names sources__* tools) keep the
        historical behavior when the domain is not mounted: the missing
        entries drop silently instead of rejecting the dispatch — only
        caller-named lists are refused."""
        app = _app(tmp_path)
        try:
            inst = await app.master.dispatch_task("survey the repos", persona="recon")
            names = inst.toolbelt.names()
            assert "read" in names
            assert not any(n.startswith("sources__") for n in names)
        finally:
            app.close()

    async def test_frozen_list_survives_resume(self, tmp_path) -> None:
        """The intersection is frozen into the TaskBook, so a checkpoint
        resume rebuilds the narrowed surface instead of widening to the root."""
        app = _app(tmp_path)
        try:
            parent = app.spawner.spawn(
                TaskBook(goal="parent", allowed_tools=("read", "grep")), name="parent"
            )
            child = await self._dispatch_under(app, parent, goal="child task")
            assert set(child.toolbelt.names()) <= {"grep", "read"}
            child.state.status = RunStatus.PAUSED
            child.state.resume = child.build_resume_snapshot().to_dict()
            app.spawner._checkpoints.save(child.state)
            run_id = child.state.run_id
        finally:
            app.close()
        app2 = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM(default="Done.")
        )
        try:
            revived = app2.spawner.resume_from_checkpoint(run_id)
            assert set(revived.toolbelt.names()) <= {"grep", "read"}
        finally:
            app2.close()


class TestRegisterSurfaceValidation:
    """register_subagent (agent calls): the definition's allowlist may not
    promise tools beyond the registering instance's surface."""

    async def test_agent_register_beyond_surface_rejects(self, tmp_path) -> None:
        from agent.runtime.current import current_instance
        from platform_capability import execute
        from platform_contracts import ActorKind, ActorRef, ServiceError

        app = _app(tmp_path)
        try:
            parent = app.spawner.spawn(
                TaskBook(goal="parent", allowed_tools=("read", "grep")), name="parent"
            )
            token = current_instance.set(parent)
            agent_ctx = ActorContext(
                actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=())
            )
            try:
                with pytest.raises(ServiceError) as exc:
                    await execute(
                        app.registry,
                        "subagent",
                        agent_ctx,
                        {
                            "action": "register",
                            "name": "cheater",
                            "description": "d",
                            "allowed_tools": ["read", "write"],
                        },
                    )
                assert "write" in str(exc.value)
            finally:
                current_instance.reset(token)
        finally:
            app.close()

    async def test_human_register_is_not_surface_bound(self, tmp_path) -> None:
        from agent.runtime.current import current_instance
        from platform_capability import execute

        app = _app(tmp_path)
        try:
            parent = app.spawner.spawn(
                TaskBook(goal="parent", allowed_tools=("read", "grep")), name="parent"
            )
            token = current_instance.set(parent)  # instance context, but USER actor
            try:
                out = await execute(
                    app.registry,
                    "subagent",
                    ActorContext(actor=LOCAL_USER),
                    {
                        "action": "register",
                        "name": "wide",
                        "description": "d",
                        "allowed_tools": ["read", "write"],
                    },
                )
                assert out["name"] == "wide"
            finally:
                current_instance.reset(token)
        finally:
            app.close()
