"""Two-level loop guard, execution deadlines and the per-turn token budget."""

from __future__ import annotations

import asyncio

from agent.build import build_agent
from agent.llm import FakeLLM, LLMReply, ToolCall, Usage
from agent.runtime.deadline import Deadline
from agent.runtime.loop_advisory import LoopAdvisory
from agent.subagent.limits import limits_from_settings
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, DomainEvent

USER_CTX = ActorContext(actor=LOCAL_USER)


class _S:
    def __init__(self, values: dict | None = None) -> None:
        self.values = values or {}

    def get(self, key: str):
        return self.values.get(key)


class TestLoopAdvisory:
    def test_first_trip_advises_once(self) -> None:
        advisory = LoopAdvisory()
        first = advisory.on_trip(tool="grep", threshold=3, window=6)
        assert first and "[advisory]" in first and "grep" in first
        assert advisory.on_trip(tool="grep", threshold=3, window=6) is None

    async def test_two_level_guard_in_turn(self, tmp_path, settle, agent_replies) -> None:
        # Three identical calls trip the detector: the first trip injects the
        # advisory nudge, the next identical call aborts the turn
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(
                [
                    LLMReply(
                        tool_calls=(
                            ToolCall("1", "list_dir", {"path": "."}),
                            ToolCall("2", "list_dir", {"path": "."}),
                            ToolCall("3", "list_dir", {"path": "."}),
                        )
                    ),
                    LLMReply(text="still repeating"),
                ]
            ),
        )
        try:
            await app.master.handle_user_message("loop")
            await settle(app)
            # The loop CONTINUED past the first trip (old behavior aborted at
            # round one with the hard break), consuming the second scripted
            # reply: that is the two-level contract, end to end
            assert agent_replies(app)[-1] == "still repeating"
        finally:
            app.close()


class TestDeadline:
    def test_from_settings_hot_values(self) -> None:
        d = Deadline.from_settings(
            _S({"agent.execution.tool_deadline_s": 5, "agent.execution.round_deadline_s": 0})
        )
        assert d.tool_s == 5 and d.round_s == 0  # 0 = off
        d = Deadline.from_settings(_S({"agent.execution.tool_deadline_s": "bad"}))
        assert d.tool_s == 90  # dirty/missing value falls back, never kills the turn

    async def test_tool_timeout_returns_structured_outcome(self) -> None:
        d = Deadline(tool_s=0.05, round_s=0)

        async def hang():
            await asyncio.sleep(5)

        outcome = await d.run_tool(hang, tool="slow_tool")
        assert outcome.ok is False and outcome.metadata["timeout"] is True
        assert "[超时]" in outcome.text and "slow_tool" in outcome.text

    async def test_self_bounded_tools_exempt_from_tool_cap(self) -> None:
        """ask_user / subagent-wait carry their own wait caps: the tool
        deadline must not amputate the block mid-wait and report a forced
        interruption that never happened (the subagent keeps running)."""
        d = Deadline(tool_s=0.05, round_s=0)

        async def slow_wait():
            await asyncio.sleep(0.2)
            return "completed"

        assert await d.run_tool(slow_wait, tool="subagent") == "completed"
        assert await d.run_tool(slow_wait, tool="ask_user") == "completed"

    async def test_round_timeout_returns_degraded_reply(self) -> None:
        d = Deadline(tool_s=0, round_s=0.05)

        async def hang():
            await asyncio.sleep(5)

        reply = await d.run_round(hang)
        assert reply.degraded and "[超时]" in (reply.text or "")


class TestTokenBudget:
    def test_limits_carry_token_budget(self) -> None:
        assert limits_from_settings(_S({"agent.rounds.max_tokens": 1000})).max_tokens == 1000
        assert limits_from_settings(_S()).max_tokens == 0  # unlimited by default
        # dispatch override can only tighten
        assert (
            limits_from_settings(_S({"agent.rounds.max_tokens": 1000}), max_tokens=50).max_tokens
            == 50
        )
        assert limits_from_settings(_S(), max_tokens=50).max_tokens == 50

    async def test_turn_ends_with_budget_report(self, tmp_path, settle) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(
                dynamic=lambda m, t: LLMReply(
                    text="working", usage=Usage(input_tokens=60, output_tokens=60)
                )
            ),
        )
        try:
            await execute(
                app.registry,
                "set_setting",
                USER_CTX,
                {"key": "agent.rounds.max_tokens", "value": 150},
            )
            await app.master.handle_user_message("go")
            await settle(app)
            replies = [
                e.payload.get("content", "")
                for _, e in app.log.read_after(types=[DomainEvent.AGENT_MESSAGE])
            ]
            assert any("[预算]" in r for r in replies)
        finally:
            app.close()
