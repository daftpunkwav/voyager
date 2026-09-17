"""Unit tests for OpenTelemetry and Langfuse span exporters and TraceDispatcher."""

from __future__ import annotations

import json
from typing import Any

import httpx
from agent.runtime.exporters import (
    InMemorySpanExporter,
    LangfuseSpanExporter,
    OtlpHttpSpanExporter,
    TraceDispatcher,
)
from agent.runtime.trace import Span, clear_spans, start_span


class TestSpanSerialization:
    def test_to_otlp_dict(self) -> None:
        span = Span(
            name="llm:round-0",
            trace_id="test-trace-123",
            start=1.0,
            end=1.5,
            ok=True,
            span_id="1234567890abcdef",
            parent_id="fedcba0987654321",
            kind="CLIENT",
            status="OK",
            attrs={"gen_ai.request.model": "gpt-4o", "gen_ai.usage.input_tokens": 100},
            start_time_ns=1_000_000_000,
            end_time_ns=1_500_000_000,
        )
        otlp = span.to_otlp_dict()
        assert len(otlp["traceId"]) == 32
        assert otlp["spanId"] == "1234567890abcdef"
        assert otlp["parentSpanId"] == "fedcba0987654321"
        assert otlp["name"] == "llm:round-0"
        assert otlp["kind"] == 3  # CLIENT
        assert otlp["status"] == {"code": 1}
        # Check attributes
        attr_keys = [a["key"] for a in otlp["attributes"]]
        assert "gen_ai.request.model" in attr_keys
        assert "gen_ai.usage.input_tokens" in attr_keys

    def test_to_langfuse_event_generation(self) -> None:
        span = Span(
            name="llm:round-0",
            trace_id="tr-1",
            start=1.0,
            end=2.0,
            ok=True,
            span_id="sp-1",
            parent_id="sp-parent",
            kind="CLIENT",
            attrs={"model": "gpt-4o", "input_tokens": 50, "output_tokens": 20},
            start_time_ns=1_700_000_000_000_000_000,
            end_time_ns=1_700_000_001_000_000_000,
        )
        evt = span.to_langfuse_event()
        assert evt["type"] == "generation-create"
        assert evt["body"]["id"] == "sp-1"
        assert evt["body"]["parentObservationId"] == "sp-parent"
        assert evt["body"]["model"] == "gpt-4o"
        assert evt["body"]["usage"] == {"input": 50, "output": 20, "total": 70}

    def test_to_langfuse_event_span(self) -> None:
        span = Span(
            name="tool:fetch",
            trace_id="tr-1",
            start=1.0,
            end=1.2,
            ok=False,
            error="timed out",
            span_id="sp-2",
            kind="INTERNAL",
            start_time_ns=1_700_000_000_000_000_000,
            end_time_ns=1_700_000_000_200_000_000,
        )
        evt = span.to_langfuse_event()
        assert evt["type"] == "span-create"
        assert evt["body"]["id"] == "sp-2"
        assert evt["body"]["level"] == "ERROR"
        assert evt["body"]["statusMessage"] == "timed out"


class TestOtlpHttpSpanExporter:
    async def test_export_otlp_payload(self) -> None:
        posted: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            posted.append(json.loads(request.content))
            return httpx.Response(200, json={"status": "ok"})

        exporter = OtlpHttpSpanExporter(
            endpoint="http://fake-collector:4318/v1/traces",
            transport=httpx.MockTransport(handler),
        )
        try:
            span = Span(
                name="test-span",
                trace_id="t1",
                start=1.0,
                end=2.0,
                ok=True,
                span_id="s1",
            )
            await exporter.export([span])
            assert len(posted) == 1
            rs = posted[0]["resourceSpans"][0]
            assert rs["scopeSpans"][0]["spans"][0]["name"] == "test-span"
        finally:
            await exporter.shutdown()


class TestLangfuseSpanExporter:
    async def test_export_langfuse_payload_with_auth(self) -> None:
        posted: list[dict[str, Any]] = []
        auth_headers: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            posted.append(json.loads(request.content))
            auth_headers.append(request.headers.get("Authorization", ""))
            return httpx.Response(200, json={"success": True})

        exporter = LangfuseSpanExporter(
            host="http://fake-langfuse:3000",
            public_key="pk-lf-test",
            secret_key="sk-lf-test",
            transport=httpx.MockTransport(handler),
        )
        try:
            span = Span(
                name="tool:calculate",
                trace_id="trace-abc",
                start=1.0,
                end=1.5,
                ok=True,
                span_id="span-123",
            )
            await exporter.export([span])
            assert len(posted) == 1
            batch = posted[0]["batch"]
            assert any(item["type"] == "trace-create" for item in batch)
            assert any(item["type"] == "span-create" for item in batch)
            assert auth_headers[0].startswith("Basic ")
        finally:
            await exporter.shutdown()


class TestTraceDispatcher:
    async def test_dispatcher_collects_and_flushes(self) -> None:
        clear_spans()
        mem_exporter = InMemorySpanExporter()
        dispatcher = TraceDispatcher([mem_exporter])
        dispatcher.attach()
        try:
            with start_span("op-1", key="val1"), start_span("op-2", key="val2"):
                pass

            await dispatcher.flush()
            names = [s.name for s in mem_exporter.spans]
            assert "op-2" in names
            assert "op-1" in names

            # Check parent-child linkage
            s2 = next(s for s in mem_exporter.spans if s.name == "op-2")
            s1 = next(s for s in mem_exporter.spans if s.name == "op-1")
            assert s2.parent_id == s1.span_id
        finally:
            await dispatcher.shutdown()
            clear_spans()
