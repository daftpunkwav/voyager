"""Rolling prune of old tool results ("microcompact").

Deterministic, in-place clearing of oversized tool outputs that sit far back
in the transcript: the last `keep_turns` turns and the newest `protect_tokens`
of tool output are always untouched; everything older is truncated to a
short sentinel when at least `min_tokens` can be recovered, so a prune only
ever fires when it pays for the cache break it causes (opencode's
protect-recent economics, claude code's microcompact marker).

Runs every round before the compaction trigger: most rounds it does nothing
(below the recovery floor), and when it does fire it is pure byte surgery —
no LLM call, no pairing changes, so tool_call/tool_result groups stay intact.
"""

from __future__ import annotations

from typing import Any

from agent.context.tokenizer import estimate_text

#: Marker left in place of a cleared tool result (visible in the transcript
#: so the model knows the content existed and can re-run the tool if needed)
PRUNE_MARK = "…[旧工具结果已清理,需要时可重新调用工具获取]"

#: Content below this length is never worth a cache break
_MIN_CONTENT_CHARS = 200

#: Turns (user-message boundaries) at the tail that are never touched
KEEP_TURNS = 2


def _turn_head_index(messages: list[dict[str, Any]], keep_turns: int) -> int:
    """Index where the protected tail starts: the `keep_turns`-th user message
    from the end. 0 (protect everything) when there are fewer turns."""
    seen = 0
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            seen += 1
            if seen >= keep_turns:
                return i
    return 0


def prune_tool_results(
    messages: list[dict[str, Any]],
    *,
    protect_tokens: int = 4000,
    min_tokens: int = 2000,
    keep_turns: int = KEEP_TURNS,
) -> int:
    """Clear oversized old tool results in place; returns the recovered token
    estimate (0 = nothing was changed).

    Candidates are role="tool" text results before the protected tail. The
    newest `protect_tokens` of candidate content stay untouched; older ones
    are replaced by PRUNE_MARK (first 80 chars kept, mirroring the mechanical
    compressor). Nothing happens when the total recoverable estimate is below
    `min_tokens` — the transcript bytes then stay identical for the cache.
    """
    if protect_tokens <= 0:
        return 0
    head = _turn_head_index(messages, max(1, keep_turns))
    # Candidates in chronological order: (index, content_tokens)
    candidates: list[tuple[int, int]] = []
    for i in range(head):
        m = messages[i]
        if m.get("role") != "tool":
            continue
        content = m.get("content")
        if not isinstance(content, str) or len(content) <= _MIN_CONTENT_CHARS:
            continue
        recovered = estimate_text(content) - estimate_text(PRUNE_MARK)
        if recovered > 0:
            candidates.append((i, recovered))
    if not candidates:
        return 0
    # Protect the newest suffix of tool output whose total fits the window;
    # everything older is cleared (a single oversized newest candidate does
    # not fit by definition, so it is cleared — pruning pays exactly there).
    used = 0
    to_clear: list[int] = []
    recovered_total = 0
    for index, tokens in reversed(candidates):
        if used + tokens <= protect_tokens:
            used += tokens
        else:
            to_clear.append(index)
            recovered_total += tokens
    if recovered_total < min_tokens:
        return 0
    for index in to_clear:
        m = messages[index]
        content = str(m.get("content", ""))
        messages[index] = {**m, "content": content[:80] + PRUNE_MARK}
    return recovered_total


__all__ = ["KEEP_TURNS", "PRUNE_MARK", "prune_tool_results"]
