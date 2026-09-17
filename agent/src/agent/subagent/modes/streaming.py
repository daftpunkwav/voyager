"""Streaming plumbing for per-round completions: delta coalescing, first-token
timing and the stream-or-complete tiering.

Pure in-memory timing shaping, unaware of the event channel; the caller
creates a fresh coalescer per round. A stream cancelled mid-flight leaves a
cancelled-anchor assistant entry in the live history: the user already saw
the streamed prefix, so the next turn's request must contain it too.
"""

from __future__ import annotations

import time
from typing import Any

from platform_contracts import CONTEXT_OVERFLOW_HINT, ServiceError

from agent.llm import LLMClient, LLMReply
from agent.runtime.deadline import Deadline
from agent.runtime.events import RuntimeEvent
from agent.subagent.modes.base import DeltaCb, EventCb, ModeBudget, noop_event

#: Delta coalescing interval (seconds): token-level deltas are batched before
#: the callback so event frequency stays bounded
DELTA_FLUSH_INTERVAL = 0.12

#: Suffix written onto a partial answer when the stream is cancelled mid-round;
#: marks the boundary between what the user actually saw and the missing rest
CANCEL_ANCHOR = "\n\n…[已中断]"


class DeltaFlusher:
    """Delta coalescer: accumulates token-level deltas and releases a batch
    only when at least `interval` has passed since the last flush."""

    def __init__(self, interval: float = DELTA_FLUSH_INTERVAL) -> None:
        self._interval = interval
        self._buf: list[str] = []
        self._last = time.monotonic()

    def add(self, text: str) -> str:
        """Accumulate a chunk; on reaching the interval return the batch to send
        (possibly empty), otherwise return an empty string."""
        self._buf.append(text)
        now = time.monotonic()
        if now - self._last >= self._interval:
            self._last = now
            out = "".join(self._buf)
            self._buf.clear()
            return out
        return ""

    def flush(self) -> str:
        out = "".join(self._buf)
        self._buf.clear()
        return out


def delta_timer(
    consumer: DeltaCb, *, on_event: EventCb = noop_event, round_n: int = 0
) -> tuple[DeltaCb, list[float]]:
    """Wrap a delta consumer with first-token timing: returns the wrapped
    callback plus a one-slot box holding the first-chunk monotonic time
    (empty when nothing streamed). The first chunk also raises LLMStreaming
    once per round. Defined outside the round loop so no closure captures a
    loop variable."""
    first_at: list[float] = []

    async def on_delta(round_no: int, text: str) -> None:
        if not first_at:
            first_at.append(time.perf_counter())
            await on_event(RuntimeEvent.LLM_STREAMING, round=round_n or round_no)
        await consumer(round_no, text)

    return on_delta, first_at


async def complete_streaming(
    llm: LLMClient,
    messages: list[dict[str, Any]],
    specs: list | None,
    on_delta: DeltaCb | None,
    *,
    round_n: int,
    on_event: EventCb = noop_event,
    on_reasoning_delta: DeltaCb | None = None,
) -> LLMReply:
    """One completion round: when on_delta is available and the llm supports
    streaming, stream and batch-callback deltas; otherwise fall back to a
    single complete (capability tiering, not a silent downgrade - streaming
    is an optional extension). Also streams thinking/reasoning deltas and
    emits THINKING_* runtime events when present.

    A ServiceError raised mid-stream (provider refused the call) folds into a
    degraded final reply - same semantics as the aggregate adapter's complete
    path - so overflow recovery sees a uniform reply shape.

    Returns the round's final LLMReply, matching complete's return semantics.
    """
    if on_delta is None and on_reasoning_delta is None:
        return await llm.complete(messages, specs)
    stream_fn = getattr(llm, "complete_stream", None)
    if not callable(stream_fn):
        return await llm.complete(messages, specs)
    flusher = DeltaFlusher()
    final: LLMReply | None = None
    emitted: list[str] = []  # batches actually handed to on_delta (what the user saw)
    thinking_started = False
    thinking_chunks: list[str] = []
    try:
        async for ev in stream_fn(messages, specs):
            if getattr(ev, "final", None) is not None:
                final = ev.final
            elif getattr(ev, "reasoning_delta", ""):
                if not thinking_started:
                    thinking_started = True
                    await on_event(RuntimeEvent.THINKING_STARTED, round=round_n)
                thinking_chunks.append(ev.reasoning_delta)
                await on_event(RuntimeEvent.THINKING_DELTA, round=round_n, delta=ev.reasoning_delta)
                if on_reasoning_delta is not None:
                    await on_reasoning_delta(round_n, ev.reasoning_delta)
            elif getattr(ev, "text_delta", ""):
                if thinking_started:
                    thinking_started = False
                    await on_event(
                        RuntimeEvent.THINKING_COMPLETED,
                        round=round_n,
                        reasoning="".join(thinking_chunks),
                    )
                batch = flusher.add(ev.text_delta)
                if batch:
                    emitted.append(batch)
                    if on_delta is not None:
                        await on_delta(round_n, batch)
    except ServiceError as exc:
        tail = flusher.flush()
        if tail and on_delta is not None:
            await on_delta(round_n, tail)
        return LLMReply(
            text=f"(LLM call failed: {exc.body.message})",
            degraded=True,
            overflow=exc.body.hint == CONTEXT_OVERFLOW_HINT,
        )
    except BaseException:
        # Cancellation/abort mid-stream: anchor the already-shown prefix into
        # the live history before propagating, so the next turn's request
        # contains the text the user saw instead of silently dropping it
        partial = "".join(emitted)
        if partial:
            messages.append({"role": "assistant", "content": partial + CANCEL_ANCHOR})
        raise
    tail = flusher.flush()
    if tail and on_delta is not None:
        await on_delta(round_n, tail)
    if thinking_started:
        await on_event(
            RuntimeEvent.THINKING_COMPLETED,
            round=round_n,
            reasoning="".join(thinking_chunks),
        )
    if final is None:
        # Out-of-contract case (stream without a final block): end with an empty
        # reply so the loop never hangs
        final = LLMReply()
    return final


async def run_phase(
    *,
    llm: LLMClient,
    messages: list[dict[str, Any]],
    on_event: EventCb = noop_event,
    deadline: Deadline | None = None,
    round_n: int = 0,
    on_delta: DeltaCb | None = None,
    budget: ModeBudget | None = None,
) -> LLMReply:
    """One phase completion for the composite modes: the standard event
    bracket (LLM_STARTED / LLM_COMPLETED), the harness deadline backstop and
    the stream-or-complete tiering. Intermediate phases pass on_delta=None -
    their products never face the user; a mode's final synthesis may pass
    the caller's on_delta so conversational runs still stream the answer.
    When a ModeBudget is given, the phase's usage and round land in the
    invocation budget (single accounting site for every completion)."""
    round_delta = None
    if on_delta is not None:
        round_delta, _first = delta_timer(on_delta, on_event=on_event, round_n=round_n)
    await on_event(RuntimeEvent.LLM_STARTED, round=round_n, streaming=on_delta is not None)
    if deadline is not None:
        reply = await deadline.run_round(
            lambda: complete_streaming(
                llm, messages, None, round_delta, round_n=round_n, on_event=on_event
            )
        )
    else:
        reply = await complete_streaming(
            llm, messages, None, round_delta, round_n=round_n, on_event=on_event
        )
    await on_event(
        RuntimeEvent.LLM_COMPLETED,
        round=round_n,
        input_tokens=reply.usage.input_tokens,
        output_tokens=reply.usage.output_tokens,
        degraded=bool(reply.degraded),
        overflow=bool(reply.overflow),
    )
    if budget is not None:
        budget.add_usage(reply.usage)
        budget.add_rounds(1)
    return reply


__all__ = [
    "CANCEL_ANCHOR",
    "DELTA_FLUSH_INTERVAL",
    "DeltaFlusher",
    "complete_streaming",
    "delta_timer",
    "run_phase",
]
