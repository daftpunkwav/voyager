"""End-to-end tests for Agent runtime tracing hierarchy and exporter wiring."""

from __future__ import annotations

from agent.build import build_agent
from agent.llm import FakeLLM, LLMReply, ToolCall, Usage
from agent.runtime.exporters import LangfuseSpanExporter, OtlpHttpSpanExporter
from agent.runtime.trace import clear_spans, recent_spans
from platform_contracts import LOCAL_USER


class TestObservabilityEndToEnd:
    async def test_trace_hierarchy_across_turn(self, tmp_path, settle) -> None:
        clear_spans()
        fake_llm = FakeLLM(
            [
                LLMReply(
                    tool_calls=(ToolCall("call_1", "glob", {"pattern": "*"}),),
                    usage=Usage(input_tokens=40, output_tokens=15),
                    model="gpt-4o",
                ),
                LLMReply(
                    text="found files",
                    usage=Usage(input_tokens=60, output_tokens=10),
                    model="gpt-4o",
                ),
            ]
        )

        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=fake_llm,
        )
        try:
            await app.master.handle_user_message("list directory contents")
            await settle(app)

            spans = recent_spans(limit=100)
            names = [s.name for s in spans]

            # 1. Verify root turn span and child spans exist
            assert "agent:turn" in names
            assert any(n.startswith("llm:round-") for n in names)
            assert any(n.startswith("tool:glob") for n in names)

            # 2. Verify parent-child relationship
            turn_span = next(s for s in spans if s.name == "agent:turn")
            round_spans = [s for s in spans if s.name.startswith("llm:round-")]
            tool_spans = [s for s in spans if s.name.startswith("tool:")]

            for rs in round_spans:
                assert rs.parent_id == turn_span.span_id

            for ts in tool_spans:
                assert ts.parent_id == turn_span.span_id
                assert ts.attrs.get("tool_name") == "glob"
                assert ts.attrs.get("tool_call_id") == "call_1"

            # 3. Verify GenAI semantic attributes
            r1 = next(s for s in round_spans if s.name == "llm:round-1")
            assert r1.attrs.get("gen_ai.request.model") == "gpt-4o"
            assert r1.attrs.get("gen_ai.usage.input_tokens") == 40
            assert r1.attrs.get("gen_ai.usage.output_tokens") == 15
        finally:
            app.close()
            clear_spans()

    async def test_exporter_settings_wiring(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
        )
        try:
            # Default is memory
            assert app.dispatcher is not None
            assert len(app.dispatcher._exporters) == 0

            # Set to all
            await app.settings.set("agent.observability.exporter", "all", LOCAL_USER)
            await app.settings.set(
                "agent.observability.langfuse_public_key", "pk-lf-test", LOCAL_USER
            )
            await app.settings.set(
                "agent.observability.langfuse_secret_key", "sk-lf-test", LOCAL_USER
            )

            # Rebuild app to verify new exporter creation
            app2 = build_agent(
                data_dir=tmp_path / "rd2",
                workspace_dir=tmp_path / "ws2",
                llm=FakeLLM(),
                settings_store=app.settings,
            )
            try:
                assert app2.dispatcher is not None
                exporters = app2.dispatcher._exporters
                assert any(isinstance(e, OtlpHttpSpanExporter) for e in exporters)
                assert any(isinstance(e, LangfuseSpanExporter) for e in exporters)
            finally:
                app2.close()
        finally:
            app.close()
            clear_spans()
