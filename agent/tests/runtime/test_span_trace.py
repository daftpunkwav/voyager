"""Span buffer: LLM rounds and tool calls record completed spans; the buffer
is bounded, trace-scoped and never raises."""

from __future__ import annotations

from agent.build import build_agent
from agent.llm import FakeLLM, LLMReply, ToolCall
from agent.runtime.trace import (
    clear_spans,
    current_trace_id,
    recent_spans,
    reset_current_trace,
    set_current_trace,
    start_span,
)


class TestSpans:
    async def test_tool_and_llm_spans_recorded(self, tmp_path, settle) -> None:
        clear_spans()
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(
                [
                    LLMReply(tool_calls=(ToolCall("1", "list_dir", {"path": "."}),)),
                    LLMReply(text="done"),
                ]
            ),
        )
        try:
            await app.master.handle_user_message("look")
            await settle(app)
            names = [s.name for s in recent_spans()]
            assert any(n.startswith("tool:list_dir") for n in names)
            assert any(n.startswith("llm:round-") for n in names)
            tool_span = next(s for s in recent_spans() if s.name.startswith("tool:"))
            assert tool_span.ok and tool_span.ms >= 0 and tool_span.attrs.get("tool_call_id") == "1"
        finally:
            app.close()
            clear_spans()

    def test_failed_block_marks_not_ok(self) -> None:
        clear_spans()
        try:
            with start_span("failing-op", detail="x"):
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        spans = recent_spans()
        assert spans and spans[0].name == "failing-op" and spans[0].ok is False
        assert spans[0].attrs == {"detail": "x"}
        clear_spans()

    def test_trace_filter_and_bounded_buffer(self) -> None:
        clear_spans()
        token = set_current_trace("t-42")
        try:
            with start_span("mine"):
                pass
        finally:
            reset_current_trace(token)
        with start_span("other"):
            pass
        assert [s.name for s in recent_spans(trace_id="t-42")] == ["mine"]
        assert {s.name for s in recent_spans()} == {"mine", "other"}
        clear_spans()
        assert recent_spans() == []


class TestTraceContext:
    def test_set_and_reset(self) -> None:
        token = set_current_trace("abc")
        assert current_trace_id() == "abc"
        reset_current_trace(token)
        assert current_trace_id() == ""
