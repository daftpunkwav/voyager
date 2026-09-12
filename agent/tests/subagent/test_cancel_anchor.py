"""Cancelled-stream anchor: a stream aborted mid-round anchors the already
shown prefix into the live history before propagating, so the next turn's
request contains what the user saw."""

from __future__ import annotations

import asyncio
from typing import Any

from agent.subagent.modes.streaming import CANCEL_ANCHOR, complete_streaming, delta_timer


class _Event:
    def __init__(self, *, text_delta: str = "") -> None:
        self.final = None
        self.text_delta = text_delta


class _LLM:  # noqa: same duck-type surface as LLMClient.complete_stream
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
