"""Raw LLM round log: TrajectoryStore raw_rounds round-trip and the REACT
on_raw wiring (one full request transcript + response per round)."""

from agent.llm import FakeLLM, LLMReply
from agent.policy import PolicyEngine
from agent.runtime.trajectory import TrajectoryStore
from agent.subagent import Mode, ModeLimits, run_mode
from agent.tools import AgentTool, Toolbelt
from platform_eventbus import EventLog


def _store(tmp_path) -> TrajectoryStore:
    return TrajectoryStore(tmp_path / "trajectory.db", EventLog(tmp_path / "events.db"))


def _msgs() -> list[dict]:
    return [{"role": "user", "content": "任务"}]


def _belt() -> Toolbelt:
    async def echo_tool(x: str = "") -> str:
        return f"echo:{x}"

    return Toolbelt(
        {"echo_tool": AgentTool(name="echo_tool", description="测试工具", handler=echo_tool)},
        PolicyEngine(),
    )


class TestRawRoundsTable:
    def test_round_trip(self, tmp_path) -> None:
        store = _store(tmp_path)
        store.record_raw_round(run_id="r1", session="chat", round=1, request="[]", response="{}")
        store.record_raw_round(run_id="r1", session="chat", round=2, request="[a]", response="[b]")
        rounds = store.raw_rounds("r1")
        assert [r["round"] for r in rounds] == [1, 2]
        assert rounds[0]["request_bytes"] == 2
        full = store.raw_round("r1", 2)
        assert full is not None and full["response"] == "[b]"
        assert store.raw_round("r1", 9) is None
        assert store.raw_rounds("missing") == []
        store.close()

    def test_overwrite_same_round_and_cap(self, tmp_path) -> None:
        store = _store(tmp_path)
        store.record_raw_round(run_id="r", session="", round=1, request="first", response="x")
        store.record_raw_round(run_id="r", session="", round=1, request="second", response="y")
        full = store.raw_round("r", 1)
        assert full is not None and full["request"] == "second"
        store.close()


class TestReactWiring:
    async def test_on_raw_receives_request_and_reply(self) -> None:
        llm = FakeLLM([LLMReply(text="完成")])
        captured: list[tuple[int, list, object]] = []

        async def on_raw(round_n: int, messages: list, reply: object) -> None:
            captured.append((round_n, messages, reply))

        messages = [{"role": "user", "content": "任务"}]
        await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=_belt(),
            messages=messages,
            limits=ModeLimits(),
            on_raw=on_raw,
        )
        assert len(captured) == 1
        round_n, req, reply = captured[0]
        assert round_n == 1 and req is messages
        assert getattr(reply, "text", "") == "完成"

    async def test_other_modes_do_not_receive_on_raw(self) -> None:
        """Non-REACT runners do not take the parameter: the dispatcher must
        not forward it (they never face the user)."""
        llm = FakeLLM([LLMReply(text="ok")])
        result = await run_mode(
            Mode.DIRECT, llm=llm, toolbelt=None, messages=_msgs(), limits=ModeLimits()
        )
        assert result == "ok"
