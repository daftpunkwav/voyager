"""Tests for build_agent runtime extension points: external settings stores
and domain tool injection.
"""

import asyncio
import json

from agent.build import resolve_prompt_model
from agent.engine import Mode, TaskBook
from agent.llm import FakeLLM, LLMReply
from agent.main import build_agent
from agent.settings import DEFS as AGENT_SETTING_DEFS
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


class TestEnvInSystem:
    """The environment layer opens the system prompt: harness identity plus
    the configured chat model (per-persona override wins), OS and workspace;
    the clock rides the trailing turn-context row instead of the head."""

    def _spawn(self, app, persona: str = "orchestrator"):
        return app.spawner.spawn(TaskBook(goal="test", mode=Mode.REACT), persona=persona)

    async def test_env_layer_reaches_spawned_system(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            inst = self._spawn(app)
            assert inst.system_prompt.startswith("【运行环境】")
            assert "You are running inside Voyager" in inst.system_prompt
            assert str(tmp_path / "ws") in inst.system_prompt  # the workspace path
            assert "Windows" in inst.system_prompt or "Linux" in inst.system_prompt
        finally:
            app.close()

    async def test_override_model_reaches_env_layer(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            await app.settings.set(
                "agent.llm.overrides",
                {"orchestrator": {"provider": "prov-a", "model": "model-x"}},
                LOCAL_USER,
            )
            inst = self._spawn(app)
            assert "Current model: prov-a/model-x" in inst.system_prompt
        finally:
            app.close()

    async def test_no_model_config_omits_model_line(self, tmp_path) -> None:
        # FakeLLM carries no model attr and the llm-domain keys are
        # unregistered in an agent-only build: the line degrades away.
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            inst = self._spawn(app)
            assert "Current model:" not in inst.system_prompt
            assert "You are running inside Voyager" in inst.system_prompt
        finally:
            app.close()

    async def test_time_rides_turn_context_row(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            inst = self._spawn(app)
            built = inst.build_turn_context(inst.task, "orchestrator", "")
            assert built.startswith("【当前时刻】")
            assert "UTC" in built
        finally:
            app.close()

    def test_resolve_prompt_model_prefers_client_attr(self, tmp_path) -> None:
        class _Client:
            model = "direct-model"

        settings = SettingsStore(tmp_path / "s.db")
        assert resolve_prompt_model(_Client(), settings, "orchestrator") == "direct-model"
        assert resolve_prompt_model(FakeLLM(), settings, "") == ""

    async def test_resolve_prompt_model_overrides_route(self, tmp_path) -> None:
        """A bare client (no model attr) resolves through the per-persona
        routing override: the provider/model pair the PersonaRoutingServiceLLM
        would actually serve, alias folded to the canonical key first."""

        class _Bare:  # no model attribute on purpose
            pass

        class _Client:
            model = "direct-model"

        settings = SettingsStore(tmp_path / "s.db")
        settings.register_fresh(AGENT_SETTING_DEFS)  # agent.llm.overrides is agent-registered
        assert resolve_prompt_model(_Bare(), settings, "orchestrator") == ""

        await settings.set(
            "agent.llm.overrides",
            {"orchestrator": {"provider": "prov-a", "model": "model-x"}},
            LOCAL_USER,
        )
        assert resolve_prompt_model(_Bare(), settings, "orchestrator") == "prov-a/model-x"
        # A legacy alias folds to the same override entry
        assert resolve_prompt_model(_Bare(), settings, "lucien") == "prov-a/model-x"
        # The client's own model attr still outranks the override
        assert resolve_prompt_model(_Client(), settings, "orchestrator") == "direct-model"


class TestPurposeRouting:
    """purpose_llms injection: the context_planner transport must drive the
    context editor's planning call (build.py meters and forwards it; without a
    route the chat client is shared)."""

    @staticmethod
    def _overbudget_msgs() -> list[dict]:
        return [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "word " * 900},
            {"role": "user", "content": "final question"},
        ]

    async def test_context_planner_route_drives_the_editor_call(self, tmp_path) -> None:
        plan = json.dumps({"keep": [0, 2], "summarize": [], "drop": [1]})
        planner = FakeLLM([LLMReply(text=plan)])
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            purpose_llms={"context_planner": planner},
        )
        try:
            inst = app.spawner.spawn(TaskBook(goal="test", mode=Mode.REACT))
            assert inst.planner_llm is not None  # routed, not the shared chat client
            report = await inst.governor().compact(self._overbudget_msgs(), target=100)
            assert report is not None and report["mode"] == "plan"
            assert len(planner.calls) == 1  # the planning call hit the routed client
        finally:
            app.close()

    async def test_without_route_the_chat_client_drives_the_editor(self, tmp_path) -> None:
        plan = json.dumps({"keep": [0, 2], "summarize": [], "drop": [1]})
        chat = FakeLLM([LLMReply(text=plan)])
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=chat)
        try:
            inst = app.spawner.spawn(TaskBook(goal="test", mode=Mode.REACT))
            report = await inst.governor().compact(self._overbudget_msgs(), target=100)
            assert report is not None and report["mode"] == "plan"
            assert len(chat.calls) == 1  # fell back to the chat client
        finally:
            app.close()
