"""Resilience tests for the master domain: safe arbitration defaults, degraded
flag, and terminal-state guarantees.
"""

import pytest
from agent.engine import Mode
from agent.engine.instance import SubagentInstance, TaskBook
from agent.llm import FakeLLM, LLMReply
from agent.master.arbiter import Arbiter, ArbiterMode
from agent.policy import PolicyEngine
from agent.runtime import Meter, is_quota_exceeded_reply, metered_llm
from agent.runtime.state import RunState, RunStatus
from agent.tools import Toolbelt


class TestArbiterSafety:
    async def test_judge_failure_enqueues_instead_of_losing(self) -> None:
        """Judge LLM raises: the message is queued (late beats lost) instead of propagating the error."""

        async def boom(_messages, _tools=None):
            raise RuntimeError("judge down")

        arbiter = Arbiter(FakeLLM(dynamic=boom))
        decision = await arbiter.decide("new message", "current task", mode=ArbiterMode.AUTO)
        assert decision.action == "enqueue"
        assert "judge" in decision.reason

    async def test_degraded_judge_reply_enqueues(self) -> None:
        """Judge returns a quota-degraded reply: treated as enqueue, not as a verdict."""
        llm = FakeLLM(
            [
                LLMReply(
                    text="（今日 LLM token 配额已用完:明天自动恢复,或在设置里调高/关闭日配额。）",
                    degraded=True,
                )
            ]
        )
        arbiter = Arbiter(llm)
        decision = await arbiter.decide("new message", "current task", mode=ArbiterMode.AUTO)
        assert decision.action == "enqueue"

    async def test_merge_still_works(self) -> None:
        arbiter = Arbiter(FakeLLM([LLMReply(text="merge")]))
        decision = await arbiter.decide("addendum", "task", mode=ArbiterMode.AUTO)
        assert decision.action == "merge"


class TestDegradedFlag:
    async def test_metered_quota_degrade_sets_flag(self) -> None:
        """Quota-degraded replies carry the degraded flag; normal replies containing the same wording are not misjudged."""
        meter = Meter()
        meter.tokens_used_today = lambda **kw: 10_000  # type: ignore[method-assign]  # test stub
        wrapped = metered_llm(FakeLLM(), meter, model="m", quota_fn=lambda: 100)
        reply = await wrapped.complete([{"role": "user", "content": "hi"}])
        assert reply.degraded is True
        assert is_quota_exceeded_reply(reply) is True

        inner = FakeLLM([LLMReply(text="今天配额用完了吗?我们聊聊。")])
        wrapped2 = metered_llm(inner, meter, model="m", quota_fn=lambda: 0)  # 0 = unlimited
        reply2 = await wrapped2.complete([{"role": "user", "content": "hi"}])
        assert (
            is_quota_exceeded_reply(reply2) is False
        )  # a genuine reply with the same wording is not misjudged

    async def test_text_fallback_path(self) -> None:
        """Plain-text path (legacy call form): substring matching is preserved."""
        assert is_quota_exceeded_reply("（今日 LLM token 配额已用完。）") is True
        assert is_quota_exceeded_reply("hello") is False
        assert is_quota_exceeded_reply(None) is False


class _SilentEvents:
    """Minimal event stub: emit returns immediately (state-machine tests do not care about telemetry)."""

    async def emit(self, *args, **kwargs) -> int:
        return 0


class TestRunModeTerminalState:
    async def test_llm_exception_leaves_failed_state_not_running(self) -> None:
        """After run_mode raises, the instance state must be FAILED, never RUNNING, so arbitration cannot deadlock."""

        async def boom(_messages, _tools=None):
            raise RuntimeError("provider exploded")

        inst = SubagentInstance(
            task=TaskBook(goal="g", mode=Mode.DIRECT),
            toolbelt=Toolbelt({}, PolicyEngine()),
            llm=FakeLLM(dynamic=boom),
            system_prompt="s",
            events=_SilentEvents(),  # type: ignore[arg-type]  # duck-typed event stub
            state=RunState(task="g"),
        )
        with pytest.raises(RuntimeError):
            await inst.run_turn("question")
        assert inst.state.status is RunStatus.FAILED
        assert "RuntimeError" in inst.state.error
