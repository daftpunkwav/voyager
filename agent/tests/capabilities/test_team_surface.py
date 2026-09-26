"""Domain capability REST surface: agent and human invoke the same
capability with the same standing."""

import asyncio

import pytest
from agent.llm import FakeLLM
from agent.main import build_agent
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ActorKind, ActorRef

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


@pytest.fixture()
def app(tmp_path):
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
    yield app
    app.memory.close()


from agent.engine import Mode, TaskBook
from platform_contracts import (
    ServiceError,
)


class TestTeamSurface:
    """Team page data sources: persona roster, user-defined subagents, and the tool surface registry."""

    async def test_list_personas_builtin_five(self, app) -> None:
        personas = await execute(app.registry, "list_personas", USER_CTX, {})
        keys = {p["key"] for p in personas}
        assert keys == {"orchestrator", "recon", "explainer", "organizer", "graph_guide"}
        master = next(p for p in personas if p["key"] == "orchestrator")
        assert master["tool_allow"] is None  # the orchestrator is not trimmed
        atlas = next(p for p in personas if p["key"] == "graph_guide")
        assert "graph__*" in atlas["tool_allow"]  # prefix grant
        assert all(p["system_prompt"] for p in personas)

    async def test_register_subagent_persisted_and_listed(self, app) -> None:
        out = await execute(
            app.registry,
            "subagent",
            USER_CTX,
            {
                "action": "register",
                "name": "scout",
                "description": "read-only scout",
                "mode": "direct",
                "allowed_tools": ["web_search", "web_fetch"],
            },
        )
        assert out == {
            "name": "scout",
            "mode": "direct",
            "allowed_tools": ["web_search", "web_fetch"],
        }
        defs = (await execute(app.registry, "subagent", USER_CTX, {"action": "list"}))[
            "definitions"
        ]
        mine = next(d for d in defs if d["name"] == "scout")
        assert mine["mode"] == "direct"
        assert mine["allowed_tools"] == ["web_search", "web_fetch"]
        assert mine["max_rounds"] is None and mine["max_tool_calls"] is None
        assert mine["network_mode"] == ""

    async def test_register_subagent_invalid_mode(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(
                app.registry,
                "subagent",
                USER_CTX,
                {
                    "action": "register",
                    "name": "bad",
                    "description": "x",
                    "mode": "flow-mode",
                },
            )
        assert exc.value.body.code == "AGENT.INVALID_INPUT"

    async def test_list_tools_includes_internal_and_bridge(self, tmp_path) -> None:
        """The roster is the ToolSpec as the LLM sees it: internal tools plus domain-bridge injected tools."""
        from agent.tools.core.base import AgentTool

        async def noop(**kw):
            return {}

        bridge = {
            "notes__create_note": AgentTool(
                name="notes__create_note", description="[notes] create note", handler=noop
            )
        }
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            extra_tools=bridge,
        )
        try:
            tools = await execute(app.registry, "tools", USER_CTX, {"action": "list"})
            names = {t["name"] for t in tools}
            assert "notes__create_note" in names  # bridge tool
            assert "subagent" in names  # internal tool
            assert "read" in names
            bridge_tool = next(t for t in tools if t["name"] == "notes__create_note")
            assert bridge_tool["description"] == "[notes] create note"  # passed through verbatim
        finally:
            app.memory.close()

    async def test_dispatch_custom_applies_allowlist(self, app) -> None:
        """Dispatching a custom subagent by name: the allowlist trim is enforced for real, not a prompt-level constraint."""
        await execute(
            app.registry,
            "subagent",
            USER_CTX,
            {
                "action": "register",
                "name": "scout2",
                "description": "read-only scout",
                "mode": "direct",
                "allowed_tools": ["web_search"],
            },
        )
        inst = await app.master.dispatch_task("do research", persona="scout2")
        names = inst.toolbelt.names()
        assert names == ["web_search"]  # write and friends are truly absent from the tool surface

    async def test_register_subagent_with_limits_and_network(self, app) -> None:
        """Creation tiers: rounds/network show up in the list card shape after registration."""
        await execute(
            app.registry,
            "subagent",
            USER_CTX,
            {
                "action": "register",
                "name": "capped",
                "description": "limited scout",
                "max_rounds": 5,
                "max_tool_calls": 9,
                "network_mode": "off",
            },
        )
        defs = (await execute(app.registry, "subagent", USER_CTX, {"action": "list"}))[
            "definitions"
        ]
        mine = next(d for d in defs if d["name"] == "capped")
        assert mine["max_rounds"] == 5
        assert mine["max_tool_calls"] == 9
        assert mine["network_mode"] == "off"
        assert mine["readonly"] is False

    async def test_register_subagent_invalid_network_mode(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(
                app.registry,
                "subagent",
                USER_CTX,
                {
                    "action": "register",
                    "name": "bad_net",
                    "description": "x",
                    "network_mode": "everything",
                },
            )
        assert exc.value.body.code == "AGENT.INVALID_INPUT"

    async def test_register_subagent_invalid_rounds(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(
                app.registry,
                "subagent",
                USER_CTX,
                {
                    "action": "register",
                    "name": "bad_rounds",
                    "description": "x",
                    "max_rounds": 0,
                },
            )
        assert exc.value.body.code == "AGENT.INVALID_INPUT"

    async def test_delete_subagent_removes_definition(self, app) -> None:
        await execute(
            app.registry,
            "subagent",
            USER_CTX,
            {"action": "register", "name": "doomed", "description": "x"},
        )
        result = await execute(
            app.registry, "subagent", USER_CTX, {"action": "unregister", "name": "doomed"}
        )
        assert result == {"deleted": "doomed"}
        defs = (await execute(app.registry, "subagent", USER_CTX, {"action": "list"}))[
            "definitions"
        ]
        assert all(d["name"] != "doomed" for d in defs)

    async def test_delete_subagent_unknown_name_raises(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(
                app.registry, "subagent", USER_CTX, {"action": "unregister", "name": "ghost"}
            )
        assert exc.value.body.code == "AGENT.NOT_FOUND"

    async def test_disabled_subagent_listed_but_refused_at_dispatch(self, app) -> None:
        """enabled=False keeps the definition visible; dispatch refuses it until re-enabled."""
        await execute(
            app.registry,
            "subagent",
            USER_CTX,
            {"action": "register", "name": "sleeper", "description": "x", "enabled": False},
        )
        defs = (await execute(app.registry, "subagent", USER_CTX, {"action": "list"}))[
            "definitions"
        ]
        assert next(d for d in defs if d["name"] == "sleeper")["enabled"] is False
        with pytest.raises(ServiceError) as exc:
            await app.master.dispatch_task("wake up", persona="sleeper")
        assert exc.value.body.code == "AGENT.FORBIDDEN"
        # Re-enable (same register path the settings toggle uses) -> dispatchable again
        await execute(
            app.registry,
            "subagent",
            USER_CTX,
            {"action": "register", "name": "sleeper", "description": "x", "enabled": True},
        )
        inst = await app.master.dispatch_task("wake up", persona="sleeper")
        assert inst.task.goal == "wake up"

    async def test_describe_tool_returns_metadata_and_schema(self, app) -> None:
        info = await execute(
            app.registry, "tools", USER_CTX, {"action": "describe", "name": "read"}
        )
        assert info["name"] == "read"
        assert info["dimension"] == "fs"
        assert info["write"] is False
        assert isinstance(info["parameters"], dict)

    async def test_describe_tool_unknown_name_raises(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(
                app.registry, "tools", USER_CTX, {"action": "describe", "name": "not_a_tool"}
            )
        assert exc.value.body.code == "AGENT.NOT_FOUND"

    async def test_list_tools_entries_carry_classification(self, app) -> None:
        """list_tools adds dimension/write classification (schema stays behind describe_tool)."""
        tools = await execute(app.registry, "tools", USER_CTX, {"action": "list"})
        read = next(t for t in tools if t["name"] == "read")
        assert read["dimension"] == "fs"
        assert read["write"] is False
        write = next(t for t in tools if t["name"] == "write")
        assert write["write"] is True
        assert "parameters" not in read

    async def test_dispatch_custom_limits_capped_stricter(self, app) -> None:
        """Dispatch clamping to the stricter side: custom rounds stricter than global win; looser ones fall back to global."""
        await execute(
            app.registry,
            "subagent",
            USER_CTX,
            {
                "action": "register",
                "name": "tight",
                "description": "small steps",
                "max_rounds": 5,
            },
        )
        await execute(
            app.registry,
            "subagent",
            USER_CTX,
            {
                "action": "register",
                "name": "loose",
                "description": "wants loose limits",
                "max_rounds": 99,
            },
        )
        tight = await app.master.dispatch_task("run one", persona="tight")
        loose = await app.master.dispatch_task("run one", persona="loose")
        assert tight.task.limits.max_rounds == 5  # global 20, custom 5 -> 5
        assert loose.task.limits.max_rounds == 20  # custom 99 -> global 20

    async def test_dispatch_custom_network_copy(self, app) -> None:
        """Network copy semantics: global whitelist + custom all -> the instance still decides with whitelist
        and rejects non-whitelisted URLs (the copy carries no settings handle, so loosening global
        settings mid-task does not back-propagate)."""
        from agent.policy import Action

        await execute(
            app.registry,
            "subagent",
            USER_CTX,
            {
                "action": "register",
                "name": "net_all",
                "description": "wants full network",
                "network_mode": "all",
            },
        )
        inst = await app.master.dispatch_task("fetch a page", persona="net_all")
        decision = inst.toolbelt._policy.decide(
            Action(dimension="network", target="https://evil.com/x")
        )
        assert not decision.allow


class TestRunningOnlyAlive:
    """list_subagents.running only contains alive instances: terminal states are not returned."""

    async def test_running_excludes_terminal_instances(self, app) -> None:
        """After an abort the instance stays in spawner.instances, but the running array no longer lists its id."""
        inst = app.spawner.spawn(
            TaskBook(goal="aborted task", mode=Mode.REACT, allowed_tools=("list_dir",)),
            persona="recon",
            name="victim",
        )
        # Manually set a terminal state to simulate in-memory residue after an abort (no real LLM run)
        inst.cancel()
        await app.spawner.cancel(inst.id)

        out = await execute(app.registry, "subagent", USER_CTX, {"action": "list"})
        assert all(r["id"] != inst.id for r in out["running"])
        # The instance remains introspectable in memory (not force-popped by design)
        assert inst.id in app.spawner.instances

    async def test_running_alive_states_are_listed(self, app) -> None:
        """All three alive states (RUNNING / WAITING_INPUT / PAUSED) appear in running."""
        from agent.runtime.state import RunStatus as RS

        ids = []
        for status in (RS.RUNNING, RS.WAITING_INPUT, RS.PAUSED):
            inst = app.spawner.spawn(
                TaskBook(goal=f"state {status.value}", mode=Mode.REACT),
                persona="recon",
                name=status.value,
            )
            inst.state.status = status
            ids.append(inst.id)

        out = await execute(app.registry, "subagent", USER_CTX, {"action": "list"})
        listed = {r["id"] for r in out["running"]}
        assert set(ids) <= listed

    async def test_chat_main_instance_still_visible_running(self, tmp_path) -> None:
        """The chat main instance stays visible while running and disappears from the list once finished (badge dependency regression)."""
        from agent.llm import LLMReply

        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM([LLMReply(text="All done.")]),
        )
        try:
            await app.master.handle_user_message("hello")
            await asyncio.sleep(0.1)
            out = await execute(app.registry, "subagent", USER_CTX, {"action": "list"})
            # The chat instance matches by name=chat (same rule as cancel_run); after answering one
            # round it sits in WAITING_INPUT, still alive, so the badge stays visible and is not dropped as finished
            assert any(r["name"] == "chat" for r in out["running"])
        finally:
            app.memory.close()
