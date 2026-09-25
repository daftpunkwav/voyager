"""Tests for the master agent: dual-track chat vs. dispatched tasks, busy
arbitration, direct-chat toggle, and dispatch notifications.
"""

import asyncio

from agent.engine import Mode
from agent.engine.limits import limits_from_settings
from agent.llm import FakeLLM, LLMReply
from agent.main import build_agent
from agent.runtime.state import RunStatus
from platform_contracts import LOCAL_USER


def _app(tmp_path, llm: FakeLLM | None = None):
    return build_agent(
        data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm or FakeLLM()
    )


class _FakeSettings:
    """Minimal settings handle (the master only reads settings, per the SettingsReader protocol)."""

    def __init__(self, values: dict) -> None:
        self._values = values

    def get(self, key: str):
        return self._values.get(key)


class TestChat:
    async def test_first_message_spawns_chat_subagent(
        self, tmp_path, settle, agent_replies
    ) -> None:
        app = _app(tmp_path, FakeLLM(default="Hi, I'm here."))
        await app.master.handle_user_message("hello")
        await settle(app)
        assert agent_replies(app) == ["Hi, I'm here."]
        chat = app.master.chat
        assert chat is not None and chat.status == RunStatus.WAITING_INPUT
        assert chat.task.mode is Mode.REACT  # Lucien chat is forced to ReAct (decision-making)
        app.memory.close()

    async def test_queue_mode_holds_second_message(self, tmp_path, settle, agent_replies) -> None:
        llm = FakeLLM(default="Got it.")
        app = _app(tmp_path, llm)
        await app.master.handle_user_message(
            "ok"
        )  # "ok" matches modes._CHITCHAT_RE: the turn ends in one round
        await settle(app)
        app.master.chat.state.status = RunStatus.RUNNING  # simulate busy
        await app.master.handle_user_message("second message")
        assert len(llm.calls) == 1  # queue mode consults no judge and does not interject
        assert len(agent_replies(app)) == 1
        app.master.chat.state.status = RunStatus.WAITING_INPUT  # restore idle
        await app.master.handle_user_message("third message")
        await settle(app)  # third message plus the queued second one both run as background turns
        assert agent_replies(app) == [
            "Got it.",
            "Got it.",
            "Got it.",
        ]  # queued second message gets processed late
        history = [m["content"] for m in app.master.chat.history if m["role"] == "user"]
        assert history == [
            "ok",
            "third message",
            "second message",
        ]  # current message first, then the queued one
        app.memory.close()

    async def test_auto_mode_merge_feeds_running_chat(self, tmp_path, settle) -> None:
        # The first scripted reply is consumed by the initial turn; the second is the judge verdict (merge)
        llm = FakeLLM(
            [
                LLMReply(text="Ok."),
                LLMReply(
                    text="Let me check the structure first."
                ),  # a non-small-talk turn with no tools triggers another complete; keep the judge slot intact
                LLMReply(text="merge"),
            ]
        )
        app = _app(tmp_path, llm)
        await app.master.handle_user_message("analyze this project")
        await settle(app)
        await app.settings.set("agent.arbiter.mode", "auto", LOCAL_USER)
        app.master.chat.state.status = RunStatus.RUNNING
        await app.master.handle_user_message("addendum: only look at the Python part")
        user_msgs = [m["content"] for m in app.master.chat.history if m["role"] == "user"]
        assert "addendum: only look at the Python part" in user_msgs  # merged into the chat context
        app.memory.close()

    async def test_turn_ending_during_arbitration_starts_new_turn(
        self, tmp_path, agent_replies, settle
    ) -> None:
        """auto/guide judge is an LLM call: when the running turn ends while the
        judge decides, the message must start its own turn instead of being
        appended to the inbox that nothing will drain any more (the stale
        RUNNING snapshot used to strand it until the next user message)."""
        llm = FakeLLM(default="Reply.")
        app = _app(tmp_path, llm)
        await app.master.handle_user_message("ok")  # chitchat: one round, one reply
        await settle(app)
        assert len(agent_replies(app)) == 1
        app.master.chat.state.status = RunStatus.RUNNING  # simulate busy

        original = app.master._arbiter.decide

        async def deciding_while_turn_ends(text, goal, *, mode):
            # The turn finishes while the judge is deciding (its completion
            # flips the instance back out of RUNNING)
            app.master.chat.state.status = RunStatus.WAITING_INPUT
            return await original(text, goal, mode=mode)

        app.master._arbiter.decide = deciding_while_turn_ends
        await app.settings.set("agent.arbiter.mode", "auto", LOCAL_USER)
        await app.master.handle_user_message("你是谁?")  # non-chitchat: judge consulted
        await settle(app)
        # The message got its own turn ("Reply.") instead of stranding in the inbox
        assert len(agent_replies(app)) == 2
        assert all(len(box) == 0 for box in app.master._inboxes.values())
        app.memory.close()

    async def test_direct_chat_skips_subagent(self, tmp_path, agent_replies, settle) -> None:
        app = _app(tmp_path, FakeLLM(default="Direct answer."))
        await app.settings.set("agent.direct_chat", True, LOCAL_USER)
        await app.master.handle_user_message("1+1=?")
        await settle(app)
        assert agent_replies(app) == ["Direct answer."]
        assert app.master.chat is None  # direct chat spawns no subagent
        app.memory.close()


class TestDispatch:
    async def test_dispatch_runs_and_reports(self, tmp_path, agent_replies, wait_until) -> None:
        app = _app(tmp_path, FakeLLM(default="Indexing done."))
        inst = await app.master.dispatch_task("index langgraph", name="index")
        await wait_until(
            lambda: (
                inst.status == RunStatus.COMPLETED
                and any("[done]" in t and "index" in t for t in agent_replies(app))
            )
        )
        assert inst.status == RunStatus.COMPLETED
        assert any("[done]" in t and "index" in t for t in agent_replies(app))
        app.memory.close()

    async def test_lucien_forced_react(self, tmp_path) -> None:
        app = _app(tmp_path, FakeLLM(default="Done."))
        inst = await app.master.dispatch_task("organize notes", persona="lucien", mode="tot")
        assert (
            inst.task.mode is Mode.REACT
        )  # persona presets cannot override this either (decision-making)
        await asyncio.sleep(0.05)
        app.memory.close()

    async def test_persona_tool_allow_trims(self, tmp_path) -> None:
        app = _app(tmp_path, FakeLLM(default="Done."))
        inst = await app.master.dispatch_task("inspect the repo", persona="atlas")
        assert "write_file" not in inst.toolbelt.names()  # atlas capability surface excludes writes
        await asyncio.sleep(0.05)
        app.memory.close()


class TestLimitsFromSettings:
    """Round-limit assembly helper: globals read live, overrides may only tighten."""

    def test_global_values_read_each_call(self) -> None:
        s = _FakeSettings({"agent.rounds.max": 7, "agent.rounds.tool_max": 9})
        limits = limits_from_settings(s)
        assert (limits.max_rounds, limits.max_tool_calls) == (7, 9)

    def test_override_stricter_wins_looser_capped(self) -> None:
        s = _FakeSettings({"agent.rounds.max": 20, "agent.rounds.tool_max": 40})
        assert limits_from_settings(s, max_rounds=5).max_rounds == 5
        assert (
            limits_from_settings(s, max_rounds=99).max_rounds == 20
        )  # looser than global -> clamped back

    def test_invalid_override_treated_as_unset(self) -> None:
        s = _FakeSettings({"agent.rounds.max": 20, "agent.rounds.tool_max": 40})
        assert limits_from_settings(s, max_rounds=0).max_rounds == 20
        assert limits_from_settings(s, max_rounds=-3).max_rounds == 20
        assert limits_from_settings(s, max_tool_calls=None).max_tool_calls == 40

    def test_missing_global_falls_back_to_dataclass_default(self) -> None:
        limits = limits_from_settings(_FakeSettings({}))
        assert (limits.max_rounds, limits.max_tool_calls) == (20, 40)


class TestChatLimitsRefresh:
    async def test_chat_limits_reread_each_turn(self, tmp_path, settle) -> None:
        """The chat instance re-reads round limits every turn: a settings change applies to the next message without rebuilding the instance."""
        app = _app(tmp_path, FakeLLM(default="Ok."))
        await app.master.handle_user_message("hello")
        await settle(app)
        chat = app.master.chat
        assert chat is not None and chat.task.limits.max_rounds == 20
        await app.settings.set("agent.rounds.max", 5, LOCAL_USER)
        await app.master.handle_user_message("continue")
        await settle(app)
        assert app.master.chat is chat  # same instance reused
        assert app.master.chat.task.limits.max_rounds == 5  # limits were replaced
        app.memory.close()


class TestSystemRefresh:
    async def test_next_turn_system_reflects_style_change(
        self, tmp_path, agent_replies, settle
    ) -> None:
        """System prompt is recomputed every turn: after changing agent.style, the next system prompt carries the new style."""
        llm = FakeLLM(default="Ok.")
        app = _app(tmp_path, llm)
        await app.master.handle_user_message("hello")
        await settle(app)
        old_sys = llm.calls[0]["messages"][0]["content"]
        await app.settings.set("agent.style", "sharp-tongued", LOCAL_USER)
        await app.master.handle_user_message("continue")
        await settle(app)
        new_sys = llm.calls[-1]["messages"][0]["content"]
        assert "【风格】sharp-tongued" in new_sys
        assert "【风格】sharp-tongued" not in old_sys
        app.memory.close()


class TestHistoryBound:
    async def test_history_capped_after_many_turns(self, tmp_path) -> None:
        """History hard cap: after many turns len(history) <= HISTORY_MAX, drops are pair-wise, head is still a user row."""
        from agent.context.budgets import HISTORY_MAX
        from agent.engine.instance import SubagentInstance, TaskBook
        from agent.policy import PolicyEngine
        from agent.runtime.events import RuntimeEvents
        from agent.runtime.state import RunState
        from agent.tools import AgentTool, Toolbelt
        from platform_eventbus import EventBus, EventLog

        async def chat_tool() -> str:
            return "ok"

        inst = SubagentInstance(
            task=TaskBook(goal="chat", conversational=True),
            toolbelt=Toolbelt(
                {"chat_tool": AgentTool(name="chat_tool", description="stub", handler=chat_tool)},
                PolicyEngine(),
            ),
            llm=FakeLLM(default="Mm."),
            system_prompt="s",
            events=RuntimeEvents(EventBus(EventLog(tmp_path / "ev.db"))),
            state=RunState(task="chat"),
        )
        for _ in range(
            35
        ):  # two rows per turn (user+assistant) -> 70 rows; must be trimmed under the cap
            await inst.run_turn("talk")
        assert len(inst.history) <= HISTORY_MAX
        assert inst.history[0]["role"] == "user"  # pair-wise drops; the head is not a half turn
        assert inst.status == RunStatus.WAITING_INPUT
