"""Tests for streaming wiring: incremental callbacks in modes, metered
passthrough, and instance delta events.

FakeStreamLLM implements both complete and complete_stream (an implementer of the
optional streaming extension); FakeLLM does not implement complete_stream (tiered
protocol, automatically falls back to non-streaming).
"""

import asyncio
from typing import cast

import pytest
from agent.llm import FakeLLM, LLMClient, LLMReply, StreamingLLClient, StreamReply, ToolCall
from agent.policy import PolicyEngine
from agent.runtime import Meter, metered_llm
from agent.runtime.events import RuntimeEvents
from agent.runtime.state import RunState, RunStatus
from agent.subagent import Mode, ModeLimits, run_mode
from agent.subagent.instance import SubagentInstance, TaskBook
from agent.tools import AgentTool, Toolbelt
from platform_eventbus import EventBus


class FakeStreamLLM(FakeLLM):
    """Adds complete_stream on top of FakeLLM: emits the scripted reply in per-character chunks."""

    def complete_stream(self, messages, tools=None):
        return self._stream(messages, tools)

    async def _stream(self, messages, tools=None):
        reply = await self.complete(messages, tools)
        for ch in reply.text or "":
            yield StreamReply(text_delta=ch)
        yield StreamReply(final=reply)


class TestModesStreaming:
    async def test_react_streams_deltas_with_round(self) -> None:
        """Tool-round text plus final-round text: deltas are batched per round, and the final result is correct."""
        llm = FakeStreamLLM(
            [
                LLMReply(text="let me check", tool_calls=(ToolCall("1", "echo_tool", {"x": "a"}),)),
                LLMReply(text="final answer"),
            ]
        )
        deltas: list[tuple[int, str]] = []

        async def on_delta(round_n: int, text: str) -> None:
            deltas.append((round_n, text))

        async def echo_tool(x: str = "") -> str:
            return f"echo:{x}"

        belt = Toolbelt(
            {"echo_tool": AgentTool(name="echo_tool", description="echo", handler=echo_tool)},
            PolicyEngine(),
        )
        result = await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=belt,
            messages=[{"role": "user", "content": "task"}],
            limits=ModeLimits(),
            on_delta=on_delta,
        )
        assert result == "final answer"
        rounds = {r for r, _ in deltas}
        assert rounds == {1, 2}
        assert "".join(t for r, t in deltas if r == 2) == "final answer"

    async def test_no_stream_support_falls_back_to_complete(self) -> None:
        """LLM without complete_stream: complete is used as usual and on_delta never fires."""
        llm = FakeLLM([LLMReply(text="answer")])
        deltas: list[tuple[int, str]] = []

        async def on_delta(round_n: int, text: str) -> None:
            deltas.append((round_n, text))

        result = await run_mode(
            Mode.DIRECT,
            llm=llm,
            toolbelt=None,
            messages=[{"role": "user", "content": "task"}],
            limits=ModeLimits(),
            on_delta=on_delta,
        )
        assert result == "answer"
        assert deltas == []

    async def test_direct_mode_streams(self) -> None:
        llm = FakeStreamLLM([LLMReply(text="direct answer")])
        deltas: list[tuple[int, str]] = []

        async def on_delta(round_n: int, text: str) -> None:
            deltas.append((round_n, text))

        result = await run_mode(
            Mode.DIRECT,
            llm=llm,
            toolbelt=None,
            messages=[{"role": "user", "content": "task"}],
            limits=ModeLimits(),
            on_delta=on_delta,
        )
        assert result == "direct answer"
        assert "".join(t for _, t in deltas) == "direct answer"

    async def test_no_on_delta_never_streams(self) -> None:
        """No on_delta given (no consumer): complete is used even when the LLM supports streaming."""
        llm = FakeStreamLLM([LLMReply(text="answer")])
        result = await run_mode(
            Mode.DIRECT,
            llm=llm,
            toolbelt=None,
            messages=[{"role": "user", "content": "task"}],
            limits=ModeLimits(),
        )
        assert result == "answer"
        # complete is still called (recorded in FakeLLM.calls); the streaming channel stays off
        assert llm.calls


class TestMeteredStreaming:
    def _meter(self) -> Meter:
        return Meter()

    async def test_stream_passthrough_meters_once(self) -> None:
        meter = self._meter()
        inner = FakeStreamLLM([])
        inner._dynamic = lambda _m, _t=None: LLMReply(text="hello")
        wrapped = metered_llm(inner, meter, model="m1")
        out = [
            ev
            async for ev in cast(StreamingLLClient, wrapped).complete_stream(
                [{"role": "user", "content": "hi"}]
            )
        ]
        assert "".join(e.text_delta for e in out) == "hello"
        final = out[-1].final
        assert final is not None
        assert final.text == "hello"
        llm_records = [r for r in meter.records if r.kind == "llm"]
        assert len(llm_records) == 1  # one stream = one meter record (aligned with complete)

    async def test_quota_exceeded_no_stream(self) -> None:
        meter = self._meter()
        inner = FakeStreamLLM([LLMReply(text="must not be consumed")])
        wrapped = metered_llm(
            inner,
            meter,
            model="m1",
            quota_fn=lambda: 100,
        )
        # Push today's usage up to the quota
        from agent.runtime import MeterRecord

        meter.record(MeterRecord(kind="llm", name="m1", ms=1.0, input_tokens=100))
        events = [
            ev
            async for ev in cast(StreamingLLClient, wrapped).complete_stream(
                [{"role": "user", "content": "hi"}]
            )
        ]
        assert len(events) == 1
        assert events[0].final is not None
        assert "配额" in (events[0].final.text or "")
        assert inner.calls == []  # no real call was made

    async def test_inner_without_stream_has_no_stream_attr(self) -> None:
        wrapped = metered_llm(FakeLLM(), Meter())
        assert not callable(getattr(wrapped, "complete_stream", None))

    async def test_complete_still_wrapped_with_quota(self) -> None:
        meter = self._meter()
        wrapped = metered_llm(FakeStreamLLM([LLMReply(text="ok")]), meter, model="m1")
        reply = await wrapped.complete([{"role": "user", "content": "hi"}])
        assert reply.text == "ok"
        assert len([r for r in meter.records if r.kind == "llm"]) == 1

    async def test_cancelled_stream_records_failure(self) -> None:
        """A stream cancelled midway: the meter records a failure, not a success."""

        class CancelledStreamLLM(FakeStreamLLM):
            def complete_stream(self, messages, tools=None):
                return self._cs(messages, tools)

            async def _cs(self, messages, tools=None):
                yield StreamReply(text_delta="half")
                raise asyncio.CancelledError

        meter = self._meter()
        wrapped = metered_llm(CancelledStreamLLM([]), meter, model="m1")
        with pytest.raises(asyncio.CancelledError):
            async for _ in cast(StreamingLLClient, wrapped).complete_stream(
                [{"role": "user", "content": "hi"}]
            ):
                pass
        (rec,) = [r for r in meter.records if r.kind == "llm"]
        assert rec.ok is False

    async def test_failing_complete_records_failure(self) -> None:
        """complete raising: ok=False, no success recorded."""
        meter = self._meter()

        class BoomLLM(FakeLLM):
            async def complete(self, messages, tools=None):
                raise RuntimeError("boom")

        wrapped = metered_llm(cast(LLMClient, BoomLLM()), meter, model="m1")
        with pytest.raises(RuntimeError):
            await wrapped.complete([{"role": "user", "content": "hi"}])
        (rec,) = [r for r in meter.records if r.kind == "llm"]
        assert rec.ok is False


class _CaptureBus:
    """Minimal EventBus stub: records published events (runtime.events only uses publish)."""

    def __init__(self, sink: list) -> None:
        self._sink = sink

    async def publish(self, event) -> int:
        self._sink.append(event)
        return len(self._sink)


class TestInstanceDeltaEvents:
    def _instance(self, *, conversational: bool, bus_events: list) -> SubagentInstance:
        captured = RuntimeEvents(cast(EventBus, _CaptureBus(bus_events)))

        async def echo_tool(x: str = "") -> str:
            return f"echo:{x}"

        return SubagentInstance(
            task=TaskBook(goal="goal", conversational=conversational),
            toolbelt=Toolbelt(
                {"echo_tool": AgentTool(name="echo_tool", description="echo", handler=echo_tool)},
                PolicyEngine(),
            ),
            llm=FakeStreamLLM([LLMReply(text="turn reply")]),
            system_prompt="sys",
            events=captured,
            state=RunState(task="goal"),
            name="chat",
        )

    async def test_conversational_emits_agent_delta(self) -> None:
        events: list = []
        inst = self._instance(conversational=True, bus_events=events)
        await inst.run_turn("ok")  # "ok" matches modes._CHITCHAT_RE: single-round turn
        deltas = [e for e in events if e.type == "agent.delta"]
        assert deltas, "conversational instance should emit delta events"
        assert "".join(d.payload["text"] for d in deltas) == "turn reply"
        assert all(d.payload["subagent"] == "chat" for d in deltas)

    async def test_task_instance_no_delta_events(self) -> None:
        """Task instances emit no deltas: concurrent background instances would interleave; results go through the completion message."""
        events: list = []
        inst = self._instance(conversational=False, bus_events=events)
        await inst.run_turn()
        assert [e for e in events if e.type == "agent.delta"] == []
        assert inst.state.status == RunStatus.COMPLETED
