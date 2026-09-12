"""Current call-chain trace context plus a bounded span buffer.

When the master/event loop processes an event carrying a trace, the trace_id goes into a
ContextVar; the bridging layer (packages/host/bridge) reads it when issuing capability calls, so the
agent's cross-service calls and the user.message they trigger share one chain -- auditing and
debugging can replay the whole chain. asyncio.create_task copies the current context, so
background dispatched tasks inherit it automatically.

Spans (phase 17): start_span/end_span around LLM and tool calls record
(name, trace_id, start/end, attrs, ok) into a bounded in-process buffer —
local output only, no external OTLP exporter. The buffer is diagnostics:
bounded (oldest evicted), never raises, and readable via recent_spans()
(REPL /replay diagnostics); the durable execution record is the trajectory
projection.
"""

from __future__ import annotations

import time
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Self

_current: ContextVar[str] = ContextVar("agent_current_trace", default="")


def set_current_trace(trace_id: str) -> object:
    """Set the current trace and return a token for reset_current_trace to restore."""
    return _current.set(trace_id)


def reset_current_trace(token: object) -> None:
    _current.reset(token)  # type: ignore[arg-type]


def current_trace_id() -> str:
    """The current chain trace; empty means not inside any event handling chain (the caller
    decides the fallback)."""
    return _current.get()


@dataclass
class Span:
    """One completed span: an operation with wall time and structured attrs."""

    name: str
    trace_id: str
    start: float
    end: float
    ok: bool
    attrs: dict[str, Any] = field(default_factory=dict)

    @property
    def ms(self) -> float:
        return round((self.end - self.start) * 1000, 1)


#: Completed-span buffer; one deque per process, bounded (oldest evicted)
_SPANS: deque[Span] = deque(maxlen=1024)
_SPAN_STACK: ContextVar[tuple[SpanHandle, ...]] = ContextVar("agent_span_stack", default=())


class SpanHandle:
    """Context manager returned by start_span; end() records the span."""

    def __init__(self, name: str, **attrs: Any) -> None:
        self._name = name
        self._attrs = attrs
        self._start = 0.0

    def __enter__(self) -> Self:
        self._start = time.perf_counter()
        stack: tuple[SpanHandle, ...] = (*_SPAN_STACK.get(), self)
        _SPAN_STACK.set(stack)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        stack = _SPAN_STACK.get()
        _SPAN_STACK.set(stack[:-1])
        span = Span(
            name=self._name,
            trace_id=current_trace_id(),
            start=self._start,
            end=time.perf_counter(),
            ok=exc is None,
            attrs=self._attrs,
        )
        _SPANS.append(span)

    async def __aenter__(self) -> Self:
        return self.__enter__()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.__exit__(exc_type, exc, tb)


def start_span(name: str, **attrs: Any) -> SpanHandle:
    """Begin a span around a block (sync or async with-statement)."""
    return SpanHandle(name, **attrs)


def recent_spans(trace_id: str = "", limit: int = 50) -> list[Span]:
    """Newest-first completed spans, optionally filtered to one trace."""
    out = [s for s in reversed(_SPANS) if not trace_id or s.trace_id == trace_id]
    return out[:limit]


def clear_spans() -> None:
    _SPANS.clear()


__all__ = [
    "Span",
    "SpanHandle",
    "clear_spans",
    "current_trace_id",
    "recent_spans",
    "reset_current_trace",
    "set_current_trace",
    "start_span",
]
