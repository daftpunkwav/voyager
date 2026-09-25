"""Streaming UX: long-tool progress forwarding and thinking-stream events."""

from __future__ import annotations

from typing import Any

from agent.engine.modes import react as react_mode
from agent.engine.modes.streaming import complete_streaming
from agent.llm import LLMReply, StreamReply, ToolCall
from agent.policy import PolicyEngine
from agent.runtime.events import RuntimeEvent
from agent.tools import AgentTool, Toolbelt


def _belt_with(handler: Any, name: str = "long_tool") -> Toolbelt:
    return Toolbelt(
        {name: AgentTool(name=name, description="long task", handler=handler)},
        PolicyEngine(),
    )


async def test_invoke_forwards_progress_to_declaring_handler() -> None:
    seen: list[tuple[float, str]] = []

    async def long_task(progress_cb=None) -> str:
        assert progress_cb is not None
        await progress_cb(0.5, "halfway")
        await progress_cb(1.0, "done")
        return "ok"

    belt = _belt_with(long_task)

    async def on_progress(p: float, msg: str) -> None:
        seen.append((p, msg))

    outcome = await belt.call_detailed(
        ToolCall(id="c1", name="long_tool", arguments={}), on_progress=on_progress
    )
    assert outcome.ok is True
    assert outcome.text == "ok"
    assert seen == [(0.5, "halfway"), (1.0, "done")]


async def test_invoke_ignores_progress_for_plain_handler() -> None:
    async def plain(x: str = "") -> str:
        return f"echo:{x}"

    belt = _belt_with(plain)

    async def on_progress(p: float, msg: str) -> None:
        raise AssertionError("plain handler must not receive progress")

    outcome = await belt.call_detailed(
        ToolCall(id="c1", name="long_tool", arguments={"x": "a"}),
        on_progress=on_progress,
    )
    assert outcome.ok is True
    assert outcome.text == "echo:a"


async def test_react_run_tool_emits_tool_progress() -> None:
    async def long_task(progress_cb=None) -> str:
        await progress_cb(0.25, "starting")
        return "done"

    belt = _belt_with(long_task)
    events: list[tuple[str, dict]] = []

    async def on_event(type_: str, **payload: Any) -> None:
        events.append((type_, payload))

    outcome, _ms = await react_mode._run_tool(
        belt, ToolCall(id="c9", name="long_tool", arguments={}), on_event
    )
    assert outcome.ok is True
    progress = [p for t, p in events if t == RuntimeEvent.TOOL_PROGRESS]
    assert len(progress) == 1
    assert progress[0]["tool"] == "long_tool"
    assert progress[0]["tool_call_id"] == "c9"
    assert progress[0]["progress"] == 0.25
    assert progress[0]["message"] == "starting"


class _ThinkingLLM:
    """Fake streaming LLM: two reasoning chunks, two text chunks, one final."""

    def complete_stream(self, messages: Any, specs: Any = None):  # type: ignore[no-untyped-def]
        async def stream():  # type: ignore[no-untyped-def]
            yield StreamReply(reasoning_delta="think-1 ")
            yield StreamReply(reasoning_delta="think-2")
            yield StreamReply(text_delta="Hello ")
            yield StreamReply(text_delta="world")
            yield StreamReply(final=LLMReply(text="Hello world", reasoning="think-1 think-2"))

        return stream()


async def test_thinking_stream_events() -> None:
    llm: Any = _ThinkingLLM()
    messages: list[dict[str, Any]] = [{"role": "user", "content": "hi"}]
    events: list[tuple[str, dict]] = []

    async def on_event(type_: str, **payload: Any) -> None:
        events.append((type_, payload))

    async def on_delta(round_no: int, text: str) -> None:
        return None

    # Bypass the time-based coalescer determinism: call with interval 0 via
    # direct deltas is timing-sensitive, so only assert event ordering and
    # final aggregation here.
    reply = await complete_streaming(llm, messages, None, on_delta, round_n=1, on_event=on_event)
    kinds = [t for t, _ in events]
    assert kinds[0] == RuntimeEvent.THINKING_STARTED
    assert RuntimeEvent.THINKING_DELTA in kinds
    assert kinds[-1] == RuntimeEvent.THINKING_COMPLETED
    deltas = [p.get("delta", "") for t, p in events if t == RuntimeEvent.THINKING_DELTA]
    assert "".join(deltas) == "think-1 think-2"
    assert reply.text == "Hello world"
    assert reply.reasoning == "think-1 think-2"


async def test_reasoning_never_merges_into_answer_text() -> None:
    llm: Any = _ThinkingLLM()
    messages: list[dict[str, Any]] = [{"role": "user", "content": "hi"}]
    shown: list[str] = []

    async def on_delta(round_no: int, text: str) -> None:
        shown.append(text)

    async def on_event(type_: str, **payload: Any) -> None:
        return None

    reply = await complete_streaming(llm, messages, None, on_delta, round_n=2, on_event=on_event)
    assert "think-1" not in "".join(shown)
    assert reply.text == "Hello world"
