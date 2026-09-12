"""CJK-aware lightweight token estimation that depends on no tokenizer
library.

Rule of thumb: fullwidth/CJK characters count as ~1 token each; everything else (Latin,
digits, halfwidth punctuation) counts as ~1 token per 4 characters. The previous len//2
heuristic systematically under-counted Chinese by about half, which triggered compression
too late. Estimates serve budget control (when to trigger compression) only, not billing --
billing relies on provider-reported usage (Meter / meter_store).
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any

#: Per-message floor for framing overhead (tokens taken by role and structure alone)
_PER_MESSAGE_FLOOR = 4


def _is_wide(ch: str) -> bool:
    return unicodedata.east_asian_width(ch) in ("F", "W")


def estimate_text(text: str) -> int:
    """Estimate a single text: CJK counts 1 token per character; everything else 1 per 4
    characters (rounded up, conservative)."""
    if not text:
        return 0
    wide = sum(1 for ch in text if _is_wide(ch))
    narrow = len(text) - wide
    return wide + -(-narrow // 4)


def estimate_messages(messages: list[dict[str, Any]]) -> int:
    """Estimate a messages list: each message gets the framing floor; the JSON arguments of
    assistant.tool_calls are counted too (previously ignored, which skewed budgets on
    multi-tool turns)."""
    total = 0
    for m in messages:
        text = str(m.get("content", ""))
        calls = m.get("tool_calls") or ()
        if calls:
            text += json.dumps(calls, ensure_ascii=False, default=str)
        total += max(estimate_text(text), _PER_MESSAGE_FLOOR)
    return total


__all__ = ["estimate_messages", "estimate_text"]
