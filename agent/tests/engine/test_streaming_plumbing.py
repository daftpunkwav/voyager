"""Streaming completion plumbing beyond the cancel anchor: delta coalescing,
first-token timing, thinking events, the stream-or-complete tiering and the
ServiceError fold-to-degraded semantics.

Test type: unit (fake stream transports and callback capture).
"""

from __future__ import annotations

from typing import Any

from agent.engine.modes.base import ModeLimits
from agent.engine.modes.streaming import (
    DELTA_FLUSH_INTERVAL,
    DeltaFlusher,
    complete_streaming,
    delta_timer,
    run_phase,
)
from agent.llm import LLMReply, Usage
from agent.runtime.events import RuntimeEvent
from platform_contracts import CONTEXT_OVERFLOW_HINT, ErrorSuffix, ServiceError


class _StreamEvent:
    def __init__(
        self,
        *,
        text_delta: str = "",
        reasoning_delta: str = "",
        final: LLMReply | None = None,
    ) -> None:
        self.text_delta = text_delta
        self.reasoning_delta = reasoning_delta
        self.final = final


class _StreamingLLM:
    """Fake streaming client: yields the scripted events from complete_stream."""

    def __init__(self, events: list[_StreamEvent], final: LLMReply | None = None) -> None:
        self._events = list(events)
        if final is not None:
            self._events.append(_StreamEvent(final=final))
        self.complete_calls = 0

    def complete_stream(self, messages: Any, specs: Any):
        async def stream():
            for ev in self._events:
                yield ev

        return stream()

    async def complete(self, messages: Any, specs: Any) -> LLMReply:
        self.complete_calls += 1
        return LLMReply(text="non-streaming")


def _reply(text: str = "done") -> LLMReply:
    return LLMReply(text=text, usage=Usage(input_tokens=10, output_tokens=5))


class TestDeltaFlusher:
    def test_holds_back_until_the_interval_elapses(self) -> None:
        flusher = DeltaFlusher(interval=60.0)  # far in the future: never due
        assert flusher.add("a") == ""
        assert flusher.add("b") == ""
        assert flusher.flush() == "ab"  # flush drains the held batch

    def test_releases_batch_after_interval(self, monkeypatch) -> None:
        clock = {"t": 0.0}
        monkeypatch.setattr("agent.engine.modes.streaming.time.monotonic", lambda: clock["t"])
        flusher = DeltaFlusher(interval=1.0)
        assert flusher.add("a") == ""
        clock["t"] += 1.0
        assert flusher.add("b") == "ab"  # interval reached: the batch goes out
        assert flusher.add("c") == ""  # buffer restarts empty
        clock["t"] += 1.0
        assert flusher.add("d") == "cd"

    def test_default_interval_matches_the_constant(self) -> None:
        assert DeltaFlusher()._interval == DELTA_FLUSH_INTERVAL


class TestDeltaTimer:
    async def test_first_chunk_emits_streaming_event_once(self) -> None:
        events: list[tuple[str, dict]] = []

        async def on_event(type_: str, **payload: Any) -> None:
            events.append((type_, payload))

        async def consumer(round_no: int, text: str) -> None:
            pass

        on_delta, first_at = delta_timer(consumer, on_event=on_event, round_n=3)
        await on_delta(3, "a")
        await on_delta(3, "b")
        assert events == [(RuntimeEvent.LLM_STREAMING, {"round": 3})]
        assert len(first_at) == 1  # first-chunk time recorded once


class TestThinkingStream:
    async def test_thinking_events_bracket_text_deltas(self) -> None:
        llm: Any = _StreamingLLM(
            [
                _StreamEvent(reasoning_delta="ponder "),
                _StreamEvent(reasoning_delta="more"),
                _StreamEvent(text_delta="answer"),
            ],
            final=_reply(),
        )
        events: list[tuple[str, dict]] = []

        async def on_event(type_: str, **payload: Any) -> None:
            events.append((type_, payload))

        async def on_reasoning(round_no: int, text: str) -> None:
            pass

        out = await complete_streaming(
            llm,
            [{"role": "user", "content": "q"}],
            None,
            None,
            round_n=1,
            on_event=on_event,
            on_reasoning_delta=on_reasoning,
        )
        assert out.text == "done"
        kinds = [t for t, _p in events]
        assert kinds == [
            RuntimeEvent.THINKING_STARTED,
            RuntimeEvent.THINKING_DELTA,
            RuntimeEvent.THINKING_DELTA,
            RuntimeEvent.THINKING_COMPLETED,
        ]
        # the accumulated reasoning lands on the completed event
        assert events[-1][1]["reasoning"] == "ponder more"

    async def test_reasoning_callback_receives_each_chunk(self) -> None:
        llm: Any = _StreamingLLM(
            [_StreamEvent(reasoning_delta="a"), _StreamEvent(reasoning_delta="b")]
        )
        chunks: list[tuple[int, str]] = []

        async def on_reasoning(round_no: int, text: str) -> None:
            chunks.append((round_no, text))

        await complete_streaming(
            llm,
            [],
            None,
            None,
            round_n=2,
            on_reasoning_delta=on_reasoning,
        )
        assert chunks == [(2, "a"), (2, "b")]


class TestStreamTiering:
    async def test_no_callbacks_falls_back_to_plain_complete(self) -> None:
        llm: Any = _StreamingLLM([], final=_reply())
        out = await complete_streaming(llm, [{"role": "user"}], None, None, round_n=1)
        assert out.text == "non-streaming"  # the plain complete answered

    async def test_client_without_stream_method_falls_back(self) -> None:
        class _PlainOnly:
            def __init__(self) -> None:
                self.calls = 0

            async def complete(self, messages, specs=None):
                self.calls += 1
                return _reply()

        plain: Any = _PlainOnly()
        out = await complete_streaming(plain, [{"role": "user"}], None, None, round_n=1)
        assert out.text == "done" and plain.calls == 1

    async def test_stream_without_final_block_ends_with_empty_reply(self) -> None:
        llm: Any = _StreamingLLM([_StreamEvent(text_delta="visible")])

        async def consumer(round_no: int, text: str) -> None:
            pass

        on_delta, _ = delta_timer(consumer)
        out = await complete_streaming(llm, [{"role": "user"}], None, on_delta, round_n=1)

        assert out.text is None  # out-of-contract stream still returns a reply
        assert out.degraded is False


class TestServiceErrorFold:
    async def test_mid_stream_refusal_becomes_degraded_reply(self) -> None:
        class _RefusingStream:
            def complete_stream(self, messages, specs):
                async def stream():
                    yield _StreamEvent(text_delta="partial")
                    raise ServiceError(
                        "llm",
                        ErrorSuffix.CONFLICT,
                        "model refused",
                        hint=CONTEXT_OVERFLOW_HINT,
                    )

                return stream()

        seen: list[str] = []

        async def consumer(round_no: int, text: str) -> None:
            seen.append(text)

        on_delta, _ = delta_timer(consumer)
        messages: list[dict] = [{"role": "user", "content": "q"}]
        llm: Any = _RefusingStream()
        out = await complete_streaming(llm, messages, None, on_delta, round_n=1)
        assert out.degraded is True
        assert out.overflow is True  # the overflow hint survives the fold
        assert "(LLM call failed: model refused)" in (out.text or "")
        assert seen == ["partial"]  # what the user saw was still delivered

    async def test_plain_refusal_is_not_overflow(self) -> None:
        class _RefusingStream:
            def complete_stream(self, messages, specs):
                async def stream():
                    raise ServiceError("llm", ErrorSuffix.RATE_LIMITED, "slow down")
                    yield _StreamEvent()  # makes this an async generator

                return stream()

        async def consumer(round_no: int, text: str) -> None:
            pass

        on_delta, _ = delta_timer(consumer)
        llm: Any = _RefusingStream()
        out = await complete_streaming(llm, [], None, on_delta, round_n=1)
        assert out.degraded is True and out.overflow is False


class TestRunPhase:
    async def test_phase_bracket_and_budget_accounting(self) -> None:
        from agent.engine.modes.base import ModeBudget

        llm: Any = _StreamingLLM([], final=_reply())
        events: list[str] = []

        async def on_event(type_: str, **payload: Any) -> None:
            events.append(type_)

        budget = ModeBudget(ModeLimits())

        async def consumer(round_no: int, text: str) -> None:
            pass

        out = await run_phase(
            llm=llm,
            messages=[{"role": "user", "content": "q"}],
            on_event=on_event,
            round_n=4,
            budget=budget,
            on_delta=consumer,
        )
        assert out.text == "done"
        assert events == [RuntimeEvent.LLM_STARTED, RuntimeEvent.LLM_COMPLETED]
        assert budget.rounds_used == 1
        assert budget.tokens_used == 15
