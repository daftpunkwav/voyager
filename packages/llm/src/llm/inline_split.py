"""Splits inline pseudo-XML segments out of OpenAI-compatible content text.

Two tag families ride the ``content`` channel on some endpoints (MiniMax
M-series is the known case) instead of, or in addition to, their protocol
fields:

- ``<think>...</think>`` — reasoning that belongs on the reasoning channel
  instead of the answer text
- ``<tool_call>...</tool_call>`` — tool-call intent, usually a JSON object
  ``{"name": ..., "arguments": {...}}``; the same endpoint may also return
  the parsed call in the ``tool_calls`` field (a content echo), and some
  responses carry a garbled non-JSON variant of the block

The splitter moves both out of the answer text: thinking is re-emitted on
the reasoning channel, tool-call blocks are captured verbatim for the
caller to convert (:func:`parse_tool_blocks`) or drop when the protocol
field already carries the call. Tags may arrive split across stream
chunks, so the streaming path uses the :class:`InlineTagSplitter` state
machine with a carry tail; the one-shot :func:`split_inline` shares the
same semantics for non-streaming content.
"""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)

THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"
TOOL_OPEN = "<tool_call>"
TOOL_CLOSE = "</tool_call>"


def _partial_tag_len(buf: str, tags: tuple[str, ...]) -> int:
    """Length of the longest suffix of buf that is a proper prefix of any tag."""
    best = 0
    for tag in tags:
        for k in range(min(len(buf), len(tag) - 1), best, -1):
            if buf.endswith(tag[:k]):
                best = k
                break
    return best


class InlineTagSplitter:
    """Streaming state machine: content deltas in, separated deltas out.

    ``feed`` returns ``(answer_delta, reasoning_delta)``; tool-call block
    content never surfaces as text — it accumulates on the splitter and is
    read from :attr:`tool_blocks` after :meth:`flush`.
    """

    def __init__(self) -> None:
        self._mode = "text"  # text | think | tool
        self._tail = ""  # a possible partial tag held back until the next chunk
        self._blocks: list[str] = []
        self._block_acc: list[str] = []

    @property
    def tool_blocks(self) -> list[str]:
        """Captured ``<tool_call>`` block bodies (verbatim, tags removed)."""
        return self._blocks

    def feed(self, text: str) -> tuple[str, str]:
        """Feed one content delta; returns ``(answer_delta, reasoning_delta)``."""
        buf = self._tail + text
        self._tail = ""
        answer: list[str] = []
        reasoning: list[str] = []
        while True:
            if self._mode == "think":
                end = buf.find(THINK_CLOSE)
                if end >= 0:
                    reasoning.append(buf[:end])
                    buf = buf[end + len(THINK_CLOSE) :]
                    self._mode = "text"
                    continue
                keep = _partial_tag_len(buf, (THINK_CLOSE,))
                reasoning.append(buf[: len(buf) - keep])
                self._tail = buf[len(buf) - keep :]
                return "".join(answer), "".join(reasoning)
            if self._mode == "tool":
                end = buf.find(TOOL_CLOSE)
                if end >= 0:
                    self._block_acc.append(buf[:end])
                    buf = buf[end + len(TOOL_CLOSE) :]
                    self._blocks.append("".join(self._block_acc))
                    self._block_acc = []
                    self._mode = "text"
                    continue
                keep = _partial_tag_len(buf, (TOOL_CLOSE,))
                self._block_acc.append(buf[: len(buf) - keep])
                self._tail = buf[len(buf) - keep :]
                return "".join(answer), "".join(reasoning)
            start = buf.find(THINK_OPEN)
            tool_start = buf.find(TOOL_OPEN)
            if 0 <= start and (tool_start < 0 or start < tool_start):
                answer.append(buf[:start])
                buf = buf[start + len(THINK_OPEN) :]
                self._mode = "think"
                continue
            if 0 <= tool_start:
                answer.append(buf[:tool_start])
                buf = buf[tool_start + len(TOOL_OPEN) :]
                self._mode = "tool"
                continue
            keep = _partial_tag_len(buf, (THINK_OPEN, TOOL_OPEN))
            answer.append(buf[: len(buf) - keep])
            self._tail = buf[len(buf) - keep :]
            return "".join(answer), "".join(reasoning)

    def flush(self) -> tuple[str, str]:
        """Drain the carry tail at end of stream; call once before aggregating."""
        text, self._tail = self._tail, ""
        if not text and not self._block_acc:
            if self._mode == "tool":
                # Empty unclosed block: nothing to capture either way.
                self._mode = "text"
            return "", ""
        if self._mode == "think":
            return "", text
        if self._mode == "tool":
            # Unclosed tool block: capture what arrived so the caller can
            # decide (convert or drop); it never reaches the answer text.
            self._blocks.append("".join(self._block_acc) + text)
            self._block_acc = []
            self._mode = "text"
            return "", ""
        return text, ""


def split_inline(text: str) -> tuple[str, str, list[str]]:
    """One-shot split of a whole content string.

    Returns ``(answer, reasoning, tool_blocks)``.
    """
    splitter = InlineTagSplitter()
    answer, reasoning = splitter.feed(text)
    tail_answer, tail_reasoning = splitter.flush()
    return answer + tail_answer, reasoning + tail_reasoning, splitter.tool_blocks


def parse_tool_blocks(blocks: list[str]) -> list[dict[str, Any]]:
    """Tool-call block bodies -> normalized tool calls.

    Accepts one JSON object per block (``{"name", "arguments"}`` — the
    MiniMax/HF tool-call shape) or a JSON array of them; synthesized ids
    mark the origin. Unparseable blocks (the garbled echo variant) are
    dropped with a warning — they never belong in the answer text.
    """
    calls: list[dict[str, Any]] = []
    for i, block in enumerate(blocks):
        raw = block.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            log.warning("dropping unparseable inline tool_call block: %.80r", raw)
            continue
        entries = obj if isinstance(obj, list) else [obj]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or entry.get("function", {}).get("name") or "")
            if not name:
                continue
            args = entry.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            calls.append(
                {
                    "id": f"inline_{i}",
                    "name": name,
                    "arguments": args if isinstance(args, dict) else {},
                }
            )
    return calls


__all__ = [
    "THINK_CLOSE",
    "THINK_OPEN",
    "TOOL_CLOSE",
    "TOOL_OPEN",
    "InlineTagSplitter",
    "parse_tool_blocks",
    "split_inline",
]
