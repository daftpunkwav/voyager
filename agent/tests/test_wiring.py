"""Tests for build_agent runtime extension points: external settings stores
and domain tool injection.
"""

import asyncio

from agent.llm import FakeLLM
from agent.main import build_agent
from agent.subagent import Mode, TaskBook
from agent.tools import AgentTool
from platform_actor import ActorContext
from platform_contracts import LOCAL_USER, ActorKind, ActorRef
from platform_settings import SettingsStore

AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


def _extra_tool() -> AgentTool:
    async def handler(text: str = "") -> dict:
        return {"echo": text}

    return AgentTool(
        name="echo__ping",
        description="test domain tool",
        handler=handler,
        dimension="app",
        write=False,
        irreversible=False,
    )


class TestSharedSettings:
    def test_shared_store_reused_and_keys_registered(self, tmp_path) -> None:
        shared = SettingsStore(tmp_path / "shared-settings.db")
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            settings_store=shared,
        )
        assert app.settings is shared  # reused directly, no new instance
        keys = {d["key"] for d in shared.list_schema()}
        assert "agent.style" in keys  # agent.* keys registered into the shared store
        assert "agent.app.allowed" in keys
        assert "agent.app.denied" in keys
        app.memory.close()

    def test_close_does_not_close_shared_store(self, tmp_path) -> None:
        shared = SettingsStore(tmp_path / "shared-settings.db")
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            settings_store=shared,
        )
        app.close()
        assert shared.get(
            "agent.style"
        )  # the shared instance is owned by the assembly root and stays usable after close
        shared.close()

    def test_default_owns_store(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        app.close()  # self-owned store/log are closed by close(), no leaked handles


class TestExtraTools:
    def test_injected_into_toolbelt(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            extra_tools={"echo__ping": _extra_tool()},
        )
        assert "echo__ping" in app.spawner._toolbelt.names()
        app.close()

    def test_handler_callable_through_toolbelt(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            extra_tools={"echo__ping": _extra_tool()},
        )
        from agent.llm import ToolCall

        out = asyncio.run(
            app.spawner._toolbelt.call(
                ToolCall(id="1", name="echo__ping", arguments={"text": "hi"})
            )
        )
        assert '"echo": "hi"' in out  # dict results are serialized to JSON text for the LLM
        app.close()


class TestStyleInSystem:
    """agent.style is an overlay above the persona: changes appear in the next conversation system prompt."""

    async def test_style_reaches_spawned_system(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            await app.settings.set("agent.style", "sharp-tongued", AGENT_CTX.actor)
            inst = app.spawner.spawn(TaskBook(goal="test", mode=Mode.REACT), persona="orchestrator")
            assert "【人格】Lucien(热心、靠谱、有主见)" in inst.system_prompt
            assert "【风格】sharp-tongued" in inst.system_prompt
        finally:
            app.close()

    async def test_default_style_is_warm(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            assert app.settings.get("agent.style") == "热心"
        finally:
            app.close()


class TestConductInSystem:
    """Conduct lines enter the system prompt: non-empty values inject their layer, empty ones omit it entirely;
    guidelines look up the persona-specific key via canonical_persona_key."""

    def _spawn(self, app, persona: str):
        return app.spawner.spawn(TaskBook(goal="test", mode=Mode.REACT), persona=persona)

    async def test_conduct_reaches_spawned_system(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            await app.settings.set("agent.conduct", "be concise, no emoji", LOCAL_USER)
            inst = self._spawn(app, "orchestrator")
            assert "【用户准则】" in inst.system_prompt
            assert "be concise, no emoji" in inst.system_prompt
        finally:
            app.close()

    async def test_default_conduct_omits_layer(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            inst = self._spawn(app, "orchestrator")
            assert "【用户准则】" not in inst.system_prompt
            assert "【人格准则】" not in inst.system_prompt
        finally:
            app.close()

    async def test_guideline_scoped_to_persona(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            await app.settings.set(
                "agent.guidelines", {"orchestrator": "confirm before changing code"}, LOCAL_USER
            )
            orch = self._spawn(app, "orchestrator")
            assert "【人格准则】" in orch.system_prompt
            assert "confirm before changing code" in orch.system_prompt
            recon = self._spawn(app, "recon")
            assert "【人格准则】" not in recon.system_prompt
        finally:
            app.close()
