"""OpenTelemetry and Langfuse span exporters for agent runtime observability.

Provides:
- SpanExporter: protocol for exporting spans
- InMemorySpanExporter: in-process test / memory exporter
- OtlpHttpSpanExporter: standard OTLP/HTTP JSON exporter (v1/traces)
- LangfuseSpanExporter: Langfuse Ingestion API (v2) exporter
- TraceDispatcher: background batched queue draining spans to registered exporters
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any, Protocol

import httpx

from agent.runtime.trace import Span, add_span_listener, remove_span_listener

log = logging.getLogger("agent.runtime.exporters")


class SpanExporter(Protocol):
    """Protocol for span export destinations."""

    async def export(self, spans: Sequence[Span]) -> None:
        """Export a batch of completed spans."""
        ...

    async def shutdown(self) -> None:
        """Flush pending spans and release network resources."""
        ...


class InMemorySpanExporter:
    """In-memory exporter for testing and local inspection."""

    def __init__(self) -> None:
        self.spans: list[Span] = []

    async def export(self, spans: Sequence[Span]) -> None:
        self.spans.extend(spans)

    async def shutdown(self) -> None:
        pass

    def clear(self) -> None:
        self.spans.clear()


class OtlpHttpSpanExporter:
    """Standard OpenTelemetry OTLP HTTP JSON exporter.

    Serializes spans to standard OTLP Protobuf-mapped JSON and sends via POST
    to an OpenTelemetry collector or compatible ingest endpoint (/v1/traces).
    """

    def __init__(
        self,
        endpoint: str = "http://localhost:4318/v1/traces",
        *,
        headers: dict[str, str] | None = None,
        timeout_s: float = 5.0,
        service_name: str = "agent",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.service_name = service_name
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)
        self._client = httpx.AsyncClient(
            headers=req_headers,
            timeout=timeout_s,
            transport=transport,
        )

    async def export(self, spans: Sequence[Span]) -> None:
        if not spans:
            return
        otlp_spans = [s.to_otlp_dict() for s in spans]
        payload: dict[str, Any] = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": self.service_name}},
                            {
                                "key": "telemetry.sdk.name",
                                "value": {"stringValue": "agent-runtime"},
                            },
                            {"key": "telemetry.sdk.language", "value": {"stringValue": "python"}},
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "agent.runtime"},
                            "spans": otlp_spans,
                        }
                    ],
                }
            ]
        }
        try:
            resp = await self._client.post(self.endpoint, json=payload)
            if resp.status_code >= 400:
                log.warning("OTLP export failed with HTTP %d: %.120s", resp.status_code, resp.text)
        except Exception as exc:  # noqa: BLE001  # network errors must not break agent execution
            log.warning("OTLP span export failed: %s", exc)

    async def shutdown(self) -> None:
        await self._client.aclose()


class LangfuseSpanExporter:
    """Langfuse Ingestion API exporter.

    Pushes traces, generations, and spans to Langfuse's public ingestion endpoint
    (/api/public/ingestion) with HTTP Basic Authentication.
    """

    def __init__(
        self,
        host: str = "https://cloud.langfuse.com",
        *,
        public_key: str = "",
        secret_key: str = "",
        timeout_s: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.host = host.rstrip("/")
        self.endpoint = f"{self.host}/api/public/ingestion"
        self._auth = (
            httpx.BasicAuth(public_key, secret_key) if (public_key and secret_key) else None
        )
        self._client = httpx.AsyncClient(
            auth=self._auth,
            timeout=timeout_s,
            transport=transport,
        )

    async def export(self, spans: Sequence[Span]) -> None:
        if not spans:
            return
        batch: list[dict[str, Any]] = []
        seen_traces: set[str] = set()

        for span in spans:
            # Emit trace-create if root span or first time seeing this trace
            if span.trace_id and span.trace_id not in seen_traces and span.parent_id is None:
                seen_traces.add(span.trace_id)
                batch.append(
                    {
                        "id": f"tr-{span.trace_id}",
                        "type": "trace-create",
                        "timestamp": span.to_langfuse_event().get("timestamp", ""),
                        "body": {
                            "id": span.trace_id,
                            "name": span.name,
                            "metadata": span.attrs,
                        },
                    }
                )
            batch.append(span.to_langfuse_event())

        payload = {"batch": batch}
        try:
            resp = await self._client.post(self.endpoint, json=payload)
            if resp.status_code >= 400:
                log.warning(
                    "Langfuse export failed with HTTP %d: %.120s", resp.status_code, resp.text
                )
        except Exception as exc:  # noqa: BLE001  # export failure must never affect core agent
            log.warning("Langfuse span export failed: %s", exc)

    async def shutdown(self) -> None:
        await self._client.aclose()


class TraceDispatcher:
    """Coordinates span collection and asynchronous dispatch to exporters.

    Attaches to trace.add_span_listener and buffers spans for batch delivery.
    """

    def __init__(self, exporters: Sequence[SpanExporter] | None = None) -> None:
        self._exporters: list[SpanExporter] = list(exporters or [])
        self._buffer: list[Span] = []
        self._lock = asyncio.Lock()
        self._attached = False
        self._bg_tasks: set[asyncio.Task] = set()

    def add_exporter(self, exporter: SpanExporter) -> None:
        self._exporters.append(exporter)

    def attach(self) -> None:
        """Start listening to completed spans from trace.record_span."""
        if not self._attached:
            add_span_listener(self._on_span)
            self._attached = True

    def detach(self) -> None:
        """Stop listening to trace.record_span."""
        if self._attached:
            remove_span_listener(self._on_span)
            self._attached = False

    def _on_span(self, span: Span) -> None:
        """Synchronous callback from trace.py."""
        self._buffer.append(span)
        # If there are active exporters and an event loop is running, schedule flush
        if self._exporters:
            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(self.flush())
                self._bg_tasks.add(task)
                task.add_done_callback(self._bg_tasks.discard)
            except RuntimeError:
                pass  # No running event loop; buffered until explicit flush

    async def flush(self) -> None:
        """Export all currently buffered spans across all registered exporters."""
        if not self._exporters or not self._buffer:
            return
        async with self._lock:
            spans_to_send = list(self._buffer)
            self._buffer.clear()

        for exporter in self._exporters:
            try:
                await exporter.export(spans_to_send)
            except Exception as exc:  # noqa: BLE001
                log.warning("exporter %s failed during flush: %s", type(exporter).__name__, exc)

    async def shutdown(self) -> None:
        """Detach listener, drain in-flight tasks, flush, and shutdown all exporters."""
        self.detach()
        if self._bg_tasks:
            await asyncio.gather(*tuple(self._bg_tasks), return_exceptions=True)
        await self.flush()
        for exporter in self._exporters:
            try:
                await exporter.shutdown()
            except Exception as exc:  # noqa: BLE001
                log.warning("exporter %s failed during shutdown: %s", type(exporter).__name__, exc)


__all__ = [
    "InMemorySpanExporter",
    "LangfuseSpanExporter",
    "OtlpHttpSpanExporter",
    "SpanExporter",
    "TraceDispatcher",
]
