"""Context-window accounting: compute the usage status the LLM sees each
turn from the resolved window (runtime.tokens) and the live transcript.

- "Used" anchors on the provider-reported input_tokens of the most recent
  call (ground truth for the prefix actually sent) and never drops below the
  local CJK-aware estimate of the current transcript, so appends after the
  last call are still accounted for.

Window/limit resolution lives in runtime.tokens (pure arithmetic, shared
with the runtime output cap); this module owns the per-turn accounting and
the cache-stable status line. Estimates feed awareness and auto-compact
triggering only; billing relies on provider-reported usage (Meter /
meter_store).
"""

from __future__ import annotations

from typing import Any

from agent.prompts import P, render
from agent.runtime.tokenizer import estimate_messages
from agent.runtime.tokens import ContextWindow


class UsageTracker:
    """Last provider-reported input usage for one instance.

    Updated from ReAct step details (each "llm" step carries the round's
    input_tokens); monotonic so an earlier larger round keeps anchoring the
    status even after short later rounds.
    """

    def __init__(self) -> None:
        self.last_reported = 0

    def record(self, input_tokens: int) -> None:
        if input_tokens > 0:
            self.last_reported = max(self.last_reported, int(input_tokens))

    def reset(self) -> None:
        """Drop the provider anchor after the transcript was restructured
        (compaction): the pre-compact rounds measured a longer prefix that no
        longer exists, so keeping it would pin the status above the trigger
        forever. Until the next provider report arrives, the local estimate
        of the (now shorter) transcript anchors the status."""
        self.last_reported = 0


def usage_status(
    window: ContextWindow,
    messages: list[dict[str, Any]],
    tracker: UsageTracker,
    *,
    auto_compact_at: int,
) -> dict[str, Any]:
    """Usage facts for the current transcript, consumed by the status line,
    the context tool, and the auto-compact trigger."""
    estimate = estimate_messages(messages)
    used = max(estimate, tracker.last_reported)
    return {
        "window_tokens": window.window_tokens,
        "max_output_tokens": window.max_output_tokens,
        "usable_tokens": window.usable,
        "used_tokens": used,
        "used_pct": round(used / window.usable * 100, 1),
        "estimate_tokens": estimate,
        "reported_tokens": tracker.last_reported,
        "entries": len(messages),
        "auto_compact_at_pct": max(1, min(int(auto_compact_at), 100)),
    }


def over_threshold(status: dict[str, Any]) -> bool:
    """Whether the usage status crossed the auto-compact threshold."""
    return status["used_pct"] >= status["auto_compact_at_pct"]


#: Bucket width for the system-prompt status line. The system message is the
#: head of the token prefix: an exact per-turn counter would rewrite it every
#: turn and invalidate the provider's prompt cache for the WHOLE transcript.
#: Rounding the displayed usage to 5% buckets keeps the line byte-identical
#: across most turns (cache survives), while the auto-compact trigger keeps
#: using the exact percentage. Exact numbers stay available on demand via the
#: context tool (tool results land at the transcript tail, which does
#: not break the prefix).
STATUS_PCT_BUCKET = 5


def render_status_line(status: dict[str, Any], *, session: str = "") -> str:
    """One-line system-prompt summary: the model reads this every turn and
    decides proactively (via the context compact action) whether to free space before
    heavy work. Deliberately cache-stable: usage is bucketed (STATUS_PCT_BUCKET)
    and exact token counts are omitted — the tool path serves exact facts."""
    bucketed = int(status["used_pct"] // STATUS_PCT_BUCKET) * STATUS_PCT_BUCKET
    line = render(
        P.context.status_line.line,
        window_tokens=status["window_tokens"],
        max_output_tokens=status["max_output_tokens"],
        used_pct=bucketed,
        auto_compact_at_pct=status["auto_compact_at_pct"],
    )
    if session:
        line += render(P.context.status_line.session_suffix, session=session)
    return line


__all__ = [
    "UsageTracker",
    "over_threshold",
    "render_status_line",
    "usage_status",
]
