"""Deterministic context compression: compress the oldest tool results
first, then prune the oldest messages in pair-shaped units, when over budget.

Token estimation lives in tokenizer.py (CJK-aware). This module performs no LLM work;
LLM-based summary compaction is handled by compactor.py.
"""

from __future__ import annotations

from typing import Any

from agent.runtime.tokenizer import estimate_messages as estimate_tokens

#: Compression budget (rough token estimate); exposed as a constant, not a user-facing setting
COMPRESS_BUDGET = 6000


def _prune_span(messages: list[dict[str, Any]], start: int) -> tuple[int, int]:
    """Locate the oldest prunable unit from start; return the half-open range (begin, end)
    to delete.

    Deletion always follows the pair shape so tool pairs are never split:
    - system messages are skipped; a user message, an assistant message without tool_calls,
      or an orphan tool message is deleted as a single entry;
    - an assistant message with tool_calls is deleted together with the contiguous run of
      tool messages that follows it, so the result never contains an assistant with
      tool_calls but no tool messages, or an orphan tool message.
    """
    i = start
    n = len(messages)
    while i < n and messages[i].get("role") == "system":
        i += 1
    if i >= n:
        return (i, i)  # only system messages remain: nothing to prune
    end = i + 1
    m = messages[i]
    if m.get("role") == "assistant" and m.get("tool_calls"):
        while end < n and messages[end].get("role") == "tool":
            end += 1
    return (i, end)


def compress(
    messages: list[dict[str, Any]],
    budget: int = COMPRESS_BUDGET,
    *,
    prune: bool = True,
) -> list[dict[str, Any]]:
    """Return a compressed copy without mutating the input; system messages are never
    compressed.

    With prune=False only the first pass (truncating old tool text) runs and no message
    entries are removed. This supports in-place compaction of a ReAct transcript within a
    single turn: an assistant message with tool_calls and its following tool messages must
    stay paired, and dropping either endpoint would trigger an API 400.
    """
    out = list(messages)
    if estimate_tokens(out) <= budget:
        return out
    # Pass 1: truncate the oldest tool results to placeholders
    for i, m in enumerate(out):
        if m.get("role") == "tool" and i < len(out) - 4:
            content = m.get("content", "")
            if isinstance(content, str):
                if len(content) > 200:
                    out[i] = {**m, "content": content[:80] + " …[已压缩]"}
            elif isinstance(content, list):
                # Tool results are text-only on the wire: collapsing an old
                # multi-modal result to a placeholder string is safe.
                out[i] = {**m, "content": "…[已压缩]"}
            elif len(str(content)) > 200:
                out[i] = {**m, "content": str(content)[:80] + " …[已压缩]"}
        if estimate_tokens(out) <= budget:
            return out
    if not prune:
        return out
    # Pass 2: drop the oldest messages in pair/group units, keeping the most recent 8
    while len(out) > 8 and estimate_tokens(out) > budget:
        begin, end = _prune_span(out, 0)
        if end == begin:
            break  # only system messages left and still over budget: nothing to prune; avoid a loop
        del out[begin:end]
    return out
