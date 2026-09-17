"""Current call-chain trace context plus a bounded span buffer.

When the master/event loop processes an event carrying a trace, the trace_id goes into a
ContextVar; the bridging layer (packages/host/bridge) reads it when issuing capability calls, so the
agent's cross-service calls and the user.message they trigger share one chain -- auditing and
debugging can replay the whole chain. asyncio.create_task copies the current context, so
background dispatched tasks inherit it automatically.

Spans (phase 17): start_span/end_span around LLM and tool calls record
(name, trace_id, start/end, attrs, ok) into a bounded in-process buffer —
local output first, with optional asynchronous export to OTLP/Langfuse via
agent.runtime.exporters.TraceDispatcher (best effort, never raises).
The buffer is diagnostics: bounded (oldest evicted), never raises, and
readable via recent_spans() (REPL /replay diagnostics); the durable
execution record is the trajectory projection.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import time
from collections import deque
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
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


def _normalize_trace_id(trace_id: str) -> str:
    """Normalize any string trace_id to a 32-hex character string for OTLP."""
    if not trace_id:
        return secrets.token_hex(16)
    clean = re.sub(r"[^0-9a-fA-F]", "", trace_id).lower()
    if len(clean) == 32:
        return clean
    return hashlib.sha256(trace_id.encode("utf-8")).hexdigest()[:32]


def _normalize_span_id(span_id: str) -> str:
    """Normalize a span_id to 16 hex characters."""
    if not span_id:
        return secrets.token_hex(8)
    clean = re.sub(r"[^0-9a-fA-F]", "", span_id).lower()
    if len(clean) == 16:
        return clean
    return hashlib.sha256(span_id.encode("utf-8")).hexdigest()[:16]


def _format_otlp_attributes(attrs: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for k, v in attrs.items():
        if isinstance(v, bool):
            out.append({"key": k, "value": {"boolValue": v}})
        elif isinstance(v, int):
            out.append({"key": k, "value": {"intValue": str(v)}})
        elif isinstance(v, float):
            out.append({"key": k, "value": {"doubleValue": v}})
        elif isinstance(v, (list, tuple)):
            values = [{"stringValue": str(item)} for item in v]
            out.append({"key": k, "value": {"arrayValue": {"values": values}}})
        else:
            out.append({"key": k, "value": {"stringValue": str(v)}})
    return out


@dataclass
class Span:
    """One completed span: an operation with wall time and structured attrs."""

    name: str
    trace_id: str
    start: float
    end: float
    ok: bool
    attrs: dict[str, Any] = field(default_factory=dict)
    span_id: str = ""
    parent_id: str | None = None
    kind: str = "INTERNAL"
    status: str = "OK"
    error: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    start_time_ns: int = 0
    end_time_ns: int = 0

    @property
    def ms(self) -> float:
        return round((self.end - self.start) * 1000, 1)

    def to_otlp_dict(self) -> dict[str, Any]:
        """Convert to standard OpenTelemetry Span JSON representation."""
        trace_hex = _normalize_trace_id(self.trace_id)
        span_hex = _normalize_span_id(self.span_id)
        parent_hex = _normalize_span_id(self.parent_id) if self.parent_id else ""

        kind_map = {"INTERNAL": 1, "SERVER": 2, "CLIENT": 3, "PRODUCER": 4, "CONSUMER": 5}
        span_obj: dict[str, Any] = {
            "traceId": trace_hex,
            "spanId": span_hex,
            "name": self.name,
            "kind": kind_map.get(self.kind, 1),
            "startTimeUnixNano": str(self.start_time_ns or int(self.start * 1e9)),
            "endTimeUnixNano": str(self.end_time_ns or int(self.end * 1e9)),
            "attributes": _format_otlp_attributes(self.attrs),
            "status": {"code": 1 if self.ok else 2},
        }
        if parent_hex:
            span_obj["parentSpanId"] = parent_hex
        if not self.ok and self.error:
            span_obj["status"]["message"] = self.error
        if self.events:
            span_obj["events"] = [
                {
                    "name": str(ev.get("name", "event")),
                    "timeUnixNano": str(ev.get("time_ns", self.end_time_ns)),
                    "attributes": _format_otlp_attributes(ev.get("attributes", {})),
                }
                for ev in self.events
            ]
        return span_obj

    def to_langfuse_event(self) -> dict[str, Any]:
        """Convert to Langfuse Ingestion API batch item (generation or span).

        Attribute coercions are defensive: usage counters fall back to 0 and
        timestamps fall back to now, so one dirty span can never break a
        whole export batch.
        """
        st_sec = (self.start_time_ns / 1e9) if self.start_time_ns else self.start
        et_sec = (self.end_time_ns / 1e9) if self.end_time_ns else self.end
        try:
            start_iso = datetime.fromtimestamp(st_sec, tz=UTC).isoformat()
        except (OverflowError, OSError, ValueError):
            start_iso = datetime.now(tz=UTC).isoformat()
        try:
            end_iso = datetime.fromtimestamp(et_sec, tz=UTC).isoformat()
        except (OverflowError, OSError, ValueError):
            end_iso = datetime.now(tz=UTC).isoformat()
        trace_id = self.trace_id or _normalize_trace_id("")

        def _as_int(value: Any) -> int:
            try:
                return max(0, int(value or 0))
            except (TypeError, ValueError):
                return 0

        is_generation = self.name.startswith("llm:") or self.kind == "CLIENT"
        if is_generation:
            in_tok = _as_int(
                self.attrs.get("gen_ai.usage.input_tokens", 0) or self.attrs.get("input_tokens", 0)
            )
            out_tok = _as_int(
                self.attrs.get("gen_ai.usage.output_tokens", 0)
                or self.attrs.get("output_tokens", 0)
            )
            gen_body: dict[str, Any] = {
                "id": self.span_id,
                "traceId": trace_id,
                "name": self.name,
                "startTime": start_iso,
                "endTime": end_iso,
                "model": str(self.attrs.get("gen_ai.request.model") or self.attrs.get("model") or ""),
                "usage": {
                    "input": in_tok,
                    "output": out_tok,
                    "total": in_tok + out_tok,
                },
                "metadata": self.attrs,
                "level": "DEFAULT" if self.ok else "ERROR",
                "statusMessage": self.error if not self.ok else None,
            }
            if self.parent_id:
                gen_body["parentObservationId"] = self.parent_id
            return {
                "id": f"evt-{self.span_id}",
                "type": "generation-create",
                "timestamp": end_iso,
                "body": gen_body,
            }

        span_body: dict[str, Any] = {
            "id": self.span_id,
            "traceId": trace_id,
            "name": self.name,
            "startTime": start_iso,
            "endTime": end_iso,
            "metadata": self.attrs,
            "level": "DEFAULT" if self.ok else "ERROR",
            "statusMessage": self.error if not self.ok else None,
        }
        if self.parent_id:
            span_body["parentObservationId"] = self.parent_id
        return {
            "id": f"evt-{self.span_id}",
            "type": "span-create",
            "timestamp": end_iso,
            "body": span_body,
        }


#: Completed-span buffer; one deque per process, bounded (oldest evicted)
_SPANS: deque[Span] = deque(maxlen=1024)
_SPAN_STACK: ContextVar[tuple[SpanHandle, ...]] = ContextVar("agent_span_stack", default=())
SpanListener = Callable[[Span], None]
_SPAN_LISTENERS: list[SpanListener] = []


def add_span_listener(listener: SpanListener) -> None:
    """Register a callback invoked whenever a span finishes."""
    if listener not in _SPAN_LISTENERS:
        _SPAN_LISTENERS.append(listener)


def remove_span_listener(listener: SpanListener) -> None:
    """Unregister a span listener."""
    if listener in _SPAN_LISTENERS:
        _SPAN_LISTENERS.remove(listener)


def clear_span_listeners() -> None:
    """Clear all registered span listeners."""
    _SPAN_LISTENERS.clear()


def record_span(span: Span) -> None:
    """Record a completed span in the local buffer and dispatch to listeners."""
    _SPANS.append(span)
    for listener in tuple(_SPAN_LISTENERS):
        try:
            listener(span)
        except Exception:  # noqa: BLE001, S110  # listener failures must not fail the span caller
            pass


class SpanHandle:
    """Context manager returned by start_span; end() records the span."""

    def __init__(
        self,
        name: str,
        *,
        kind: str = "INTERNAL",
        span_id: str | None = None,
        parent_id: str | None = None,
        **attrs: Any,
    ) -> None:
        self._name = name
        self._kind = kind
        self._attrs = dict(attrs)
        self._start_perf = 0.0
        self._start_time_ns = 0
        self.span_id = span_id or secrets.token_hex(8)
        self.parent_id = parent_id
        self._events: list[dict[str, Any]] = []
        self._error: str = ""
        self._ok: bool | None = None

    def set_attribute(self, key: str, value: Any) -> None:
        self._attrs[key] = value

    def set_attributes(self, **kwargs: Any) -> None:
        self._attrs.update(kwargs)

    def set_error(self, error: str) -> None:
        self._error = error
        self._ok = False

    def add_event(self, name: str, **attrs: Any) -> None:
        self._events.append({
            "name": name,
            "time_ns": time.time_ns(),
            "attributes": attrs,
        })

    def __enter__(self) -> Self:
        self._start_perf = time.perf_counter()
        self._start_time_ns = time.time_ns()
        stack = _SPAN_STACK.get()
        if self.parent_id is None and stack:
            self.parent_id = stack[-1].span_id
        _SPAN_STACK.set((*stack, self))
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        stack = _SPAN_STACK.get()
        _SPAN_STACK.set(stack[:-1])
        end_perf = time.perf_counter()
        end_time_ns = time.time_ns()
        ok = (exc is None) if self._ok is None else self._ok
        err = str(exc) if exc is not None else self._error
        span = Span(
            name=self._name,
            trace_id=current_trace_id(),
            start=self._start_perf,
            end=end_perf,
            ok=ok,
            attrs=self._attrs,
            span_id=self.span_id,
            parent_id=self.parent_id,
            kind=self._kind,
            status="OK" if ok else "ERROR",
            error=err,
            events=self._events,
            start_time_ns=self._start_time_ns,
            end_time_ns=end_time_ns,
        )
        record_span(span)

    async def __aenter__(self) -> Self:
        return self.__enter__()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.__exit__(exc_type, exc, tb)


def start_span(
    name: str,
    *,
    kind: str = "INTERNAL",
    span_id: str | None = None,
    parent_id: str | None = None,
    **attrs: Any,
) -> SpanHandle:
    """Begin a span around a block (sync or async with-statement)."""
    return SpanHandle(name, kind=kind, span_id=span_id, parent_id=parent_id, **attrs)


def recent_spans(trace_id: str = "", limit: int = 50) -> list[Span]:
    """Newest-first completed spans, optionally filtered to one trace."""
    out = [s for s in reversed(_SPANS) if not trace_id or s.trace_id == trace_id]
    return out[:limit]


def clear_spans() -> None:
    _SPANS.clear()


__all__ = [
    "Span",
    "SpanHandle",
    "add_span_listener",
    "clear_span_listeners",
    "clear_spans",
    "current_trace_id",
    "recent_spans",
    "record_span",
    "remove_span_listener",
    "reset_current_trace",
    "set_current_trace",
    "start_span",
]
