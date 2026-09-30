"""Cancelled-stream anchor: a stream aborted mid-round anchors the already
shown prefix into the live history before propagating, so the next turn's
request contains what the user saw."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from agent.engine import Mode, TaskBook
from agent.engine.modes.streaming import CANCEL_ANCHOR, complete_streaming, delta_timer
from agent.llm import FakeLLM
from agent.main import build_agent
from agent.runtime.state import RunStatus


class _Event:
    def __init__(self, *, text_delta: str = "") -> None:
        self.final = None
        self.text_delta = text_delta


# Same duck-type surface as LLMClient.complete_stream (complete + complete_stream).
class _LLM:
    """Stream fake: yields the given chunks, then cancels mid-round."""

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    def complete_stream(self, messages, specs):
        async def stream():
            for c in self._chunks:
                yield _Event(text_delta=c)
                await asyncio.sleep(0.13)  # let the coalescing interval elapse
            raise asyncio.CancelledError()

        return stream()


async def test_cancelled_stream_anchors_shown_prefix() -> None:
    """Deltas already flushed to the UI land in the live history verbatim plus
    the cancel anchor; unflushed tail is not claimed as shown."""
    messages: list[dict] = [{"role": "user", "content": "hi"}]
    llm: Any = _LLM(["hel", "lo wo", "rld"])  # first two flush; the tail does not
    shown: list[str] = []

    async def consumer(round_no: int, text: str) -> None:
        shown.append(text)

    on_delta, _first = delta_timer(consumer)
    try:
        await complete_streaming(llm, messages, None, on_delta, round_n=1)
        raise AssertionError("CancelledError expected")
    except asyncio.CancelledError:
        pass
    shown_text = "".join(shown)
    assert shown_text  # something reached the UI before the cancel
    (entry,) = [m for m in messages if m.get("role") == "assistant"]
    assert entry["content"] == shown_text + CANCEL_ANCHOR


async def test_cancel_before_any_delta_leaves_history_untouched() -> None:
    """Nothing streamed -> nothing shown -> no anchor entry."""
    messages: list[dict] = [{"role": "user", "content": "hi"}]
    llm: Any = _LLM([])

    async def consumer(round_no: int, text: str) -> None:
        raise AssertionError("no delta expected")

    on_delta, _ = delta_timer(consumer)
    try:
        await complete_streaming(llm, messages, None, on_delta, round_n=1)
        raise AssertionError("CancelledError expected")
    except asyncio.CancelledError:
        pass
    assert [m for m in messages if m.get("role") == "assistant"] == []


class _CancelMidStreamLLM(FakeLLM):
    """complete_stream yields three flushed chunks, then cancels mid-round;
    the plain complete path fails loudly (streaming is the surface under
    test and a fallback would silently pass nothing)."""

    def complete(self, *args: Any, **kw: Any):
        raise AssertionError("non-streaming fallback must not run")

    def complete_stream(self, messages, specs):
        async def stream():
            for chunk in ("hel", "lo wo", "rld"):
                yield SimpleNamespace(final=None, text_delta=chunk, reasoning_delta="")
                await asyncio.sleep(0.13)  # past the coalescing interval: flushed
            raise asyncio.CancelledError()

        return stream()


def _shown_text(app, run_id: str) -> str:
    """What the user has been shown so far: the coalesced AgentDelta payloads
    in log order (the same batches complete_streaming counts as `emitted`)."""
    return "".join(
        str(e.payload.get("text") or "")
        for _, e in app.log.read_after(after_seq=0)
        if e.type == "agent.delta" and e.payload.get("run_id") == run_id
    )


async def test_hard_cancel_keeps_shown_prefix_in_history(tmp_path) -> None:
    """Turn-level anchor persistence: a hard cancel mid-stream must carry the
    anchored prefix from the wire list (which dies with the turn) into
    inst.history, so the next turn's request still contains what the user has
    on screen instead of silently dropping it. The cancel lands only after a
    delta reached the UI, and the anchored content is asserted against the
    observed deltas - the wall-clock arrival of coalesced batches must not
    leak into the contract."""
    app = build_agent(
        data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=_CancelMidStreamLLM()
    )
    try:
        inst = app.spawner.spawn(
            TaskBook(goal="chat", mode=Mode.REACT, conversational=True), name="chat"
        )
        task = asyncio.create_task(app.spawner.start(inst, "hello"))
        deadline = asyncio.get_running_loop().time() + 10.0
        while not _shown_text(app, inst.state.run_id):
            assert asyncio.get_running_loop().time() < deadline, "no delta ever reached the UI"
            await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)
        assert inst.state.status is RunStatus.CANCELLED
        shown = _shown_text(app, inst.state.run_id)
        assert shown
        assistant = [m for m in inst.history if m.get("role") == "assistant"]
        assert len(assistant) == 1
        assert assistant[0]["content"] == shown + CANCEL_ANCHOR
        # The user's input stays the head of the exchange (pre-existing rule)
        assert inst.history[0] == {"role": "user", "content": "hello"}
    finally:
        app.memory.close()
