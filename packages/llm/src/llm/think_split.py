"""Splits inline ``<think>...</think>`` reasoning out of content text.

Some OpenAI-compatible reasoning models (MiniMax M-series) inline their
thinking into the content channel wrapped in ``<think>`` tags instead of
sending a ``reasoning_content`` field. The splitter moves that thinking onto
the reasoning channel so it never leaks into the answer text.

Tags may arrive split across stream chunks, so the streaming path uses the
:class:`ThinkSplitter` state machine with a carry tail; the one-shot
:func:`split_inline_think` shares the same semantics for non-streaming
content.
"""

from __future__ import annotations

THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"


def _partial_tag_len(buf: str, tag: str) -> int:
    """Length of the longest suffix of buf that is a proper prefix of tag."""
    for k in range(min(len(buf), len(tag) - 1), 0, -1):
        if buf.endswith(tag[:k]):
            return k
    return 0


class ThinkSplitter:
    """Streaming state machine: content deltas in, separated deltas out."""

    def __init__(self) -> None:
        self._in_think = False
        self._tail = ""  # a possible partial tag held back until the next chunk

    def feed(self, text: str) -> tuple[str, str]:
        """Feed one content delta; returns ``(answer_delta, reasoning_delta)``."""
        buf = self._tail + text
        self._tail = ""
        answer: list[str] = []
        reasoning: list[str] = []
        while True:
            if self._in_think:
                end = buf.find(THINK_CLOSE)
                if end >= 0:
                    reasoning.append(buf[:end])
                    buf = buf[end + len(THINK_CLOSE) :]
                    self._in_think = False
                    continue
                keep = _partial_tag_len(buf, THINK_CLOSE)
                reasoning.append(buf[: len(buf) - keep])
                self._tail = buf[len(buf) - keep :]
                return "".join(answer), "".join(reasoning)
            start = buf.find(THINK_OPEN)
            if start >= 0:
                answer.append(buf[:start])
                buf = buf[start + len(THINK_OPEN) :]
                self._in_think = True
                continue
            keep = _partial_tag_len(buf, THINK_OPEN)
            answer.append(buf[: len(buf) - keep])
            self._tail = buf[len(buf) - keep :]
            return "".join(answer), "".join(reasoning)

    def flush(self) -> tuple[str, str]:
        """Drain the carry tail at end of stream; call once before aggregating."""
        text, self._tail = self._tail, ""
        if not text:
            return "", ""
        if self._in_think:
            return "", text
        return text, ""


def split_inline_think(text: str) -> tuple[str, str]:
    """One-shot split of a whole content string; returns ``(answer, reasoning)``."""
    splitter = ThinkSplitter()
    answer, reasoning = splitter.feed(text)
    tail_answer, tail_reasoning = splitter.flush()
    return answer + tail_answer, reasoning + tail_reasoning


__all__ = ["THINK_CLOSE", "THINK_OPEN", "ThinkSplitter", "split_inline_think"]
