"""Context-window accounting: resolve per-model window limits from
settings and compute the usage status the LLM sees each turn.

The model is the primary context manager, so the harness owes it accurate
facts about its own window:
- Limits resolve per model first (agent.context.model_profiles), falling back
  to the global defaults (agent.context.window_tokens /
  agent.context.max_output_tokens). Values the user enters must match the
  model's real parameters; malformed entries fall back instead of raising.
- "Used" anchors on the provider-reported input_tokens of the most recent
  call (ground truth for the prefix actually sent) and never drops below the
  local CJK-aware estimate of the current transcript, so appends after the
  last call are still accounted for.

Estimates feed awareness and auto-compact triggering only; billing relies on
provider-reported usage (Meter / meter_store).
"""

from __future__ import annotations

import logging

log = logging.getLogger("agent.context.usage")

from dataclasses import dataclass
from typing import Any

from agent.context.tokenizer import estimate_messages
from agent.contracts import SettingsReader

#: Defaults when neither the global keys nor a model profile say otherwise
DEFAULT_WINDOW_TOKENS = 200_000
DEFAULT_MAX_OUTPUT_TOKENS = 64_000


@dataclass(frozen=True)
class ContextWindow:
    """Resolved per-model window limits (tokens)."""

    window_tokens: int = DEFAULT_WINDOW_TOKENS
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS

    @property
    def usable(self) -> int:
        """Tokens available for the transcript: the window minus the room the
        reply needs. Floor at 1 so percent math never divides by zero."""
        return max(self.window_tokens - self.max_output_tokens, 1)


def _int_or(value: Any, fallback: int) -> int:
    """Non-positive or malformed values count as unset."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback


#: Models already warned about (process lifetime, one log line each): an
#: unknown model runs on the conservative global defaults, and the operator
#: should hear about it exactly once instead of every call.
_WARNED_MODELS: set[str] = set()


def resolve_window(settings: SettingsReader, model_name: str = "") -> ContextWindow:
    """Resolve the window limits: global defaults first, then the model's
    profile entry (agent.context.model_profiles) when one matches.

    Malformed shapes (non-dict profiles, non-dict entry, bad numbers) fall
    back to the next source instead of raising - a bad setting must never
    cripple context accounting. A model with no profile entry runs on the
    global defaults and logs one warning (phase 18: keep the profiles in sync
    with llm.list_models).
    """
    window = _int_or(settings.get("agent.context.window_tokens"), DEFAULT_WINDOW_TOKENS)
    output = _int_or(settings.get("agent.context.max_output_tokens"), DEFAULT_MAX_OUTPUT_TOKENS)
    profiles = settings.get("agent.context.model_profiles")
    if model_name and isinstance(profiles, dict):
        profile = profiles.get(model_name)
        if isinstance(profile, dict):
            window = _int_or(profile.get("window_tokens"), window)
            output = _int_or(profile.get("max_output_tokens"), output)
        elif model_name not in _WARNED_MODELS:
            _WARNED_MODELS.add(model_name)
            log.warning(
                'no context profile for model "%s": using the global defaults; '
                'add agent.context.model_profiles["%s"] with the real window',
                model_name,
                model_name,
            )
    return ContextWindow(window_tokens=window, max_output_tokens=output)


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
    the context_status tool, and the auto-compact trigger."""
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
#: context_status tool (tool results land at the transcript tail, which does
#: not break the prefix).
STATUS_PCT_BUCKET = 5


def render_status_line(status: dict[str, Any], *, session: str = "") -> str:
    """One-line system-prompt summary: the model reads this every turn and
    decides proactively (via the context compact action) whether to free space before
    heavy work. Deliberately cache-stable: usage is bucketed (STATUS_PCT_BUCKET)
    and exact token counts are omitted — the tool path serves exact facts."""
    bucketed = int(status["used_pct"] // STATUS_PCT_BUCKET) * STATUS_PCT_BUCKET
    line = (
        f"【上下文状态】窗口 {status['window_tokens']} tok(输出预留 "
        f"{status['max_output_tokens']}),已用约 {bucketed}%+"
        f",自动压缩阈值 {status['auto_compact_at_pct']}%。"
        "规划大批量工作前,可用 context(action=compact) 主动腾出空间。"
    )
    if session:
        line += f"当前会话: {session}。"
    return line


__all__ = [
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "DEFAULT_WINDOW_TOKENS",
    "ContextWindow",
    "UsageTracker",
    "over_threshold",
    "render_status_line",
    "resolve_window",
    "usage_status",
]
