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


def _estimate_part(part: Any) -> int:
    """Estimate tokens for a single ContentPart or dict part.

    Image parts use the provider's fixed tile cost (never the data-URL
    bytes); file parts use a small placeholder cost for the same reason:
    stringifying bulk payload bytes here would burn CPU on megabytes of
    base64 without changing the budget decision.
    """
    text = getattr(part, "text", None)
    if isinstance(text, str):
        return estimate_text(text)
    ptype = getattr(part, "type", None) or (part.get("type") if isinstance(part, dict) else "")
    if ptype == "image_url":
        detail = (
            getattr(part, "detail", "auto")
            if hasattr(part, "detail")
            else (
                part.get("image_url", {}).get("detail", "auto")
                if isinstance(part, dict) and isinstance(part.get("image_url"), dict)
                else "auto"
            )
        )
        return 85 if detail == "low" else 255
    if ptype == "file":
        return _PER_MESSAGE_FLOOR
    if isinstance(part, dict):
        if "text" in part and isinstance(part["text"], str):
            return estimate_text(part["text"])
        return estimate_text(json.dumps(part, ensure_ascii=False, default=str)[:2000])
    return estimate_text(str(part)[:2000])


def estimate_messages(messages: list[dict[str, Any]]) -> int:
    """Estimate a messages list: each message gets the framing floor; the JSON arguments of
    assistant.tool_calls are counted too (previously ignored, which skewed budgets on
    multi-tool turns), as is echoed thinking text (extended-thinking replays ride every
    request while tool use continues). Supports multi-modal ContentParts."""
    total = 0
    for m in messages:
        raw_content = m.get("content", "")
        extra_tokens = 0
        text = ""
        if isinstance(raw_content, list):
            for part in raw_content:
                extra_tokens += _estimate_part(part)
        elif isinstance(raw_content, str):
            text = raw_content
        else:
            text = str(raw_content)

        calls = m.get("tool_calls") or ()
        if calls:
            text += json.dumps(calls, ensure_ascii=False, default=str)
        thinking = m.get("thinking_blocks") or ()
        if isinstance(thinking, (list, tuple)):
            for block in thinking:
                if isinstance(block, dict) and isinstance(block.get("thinking"), str):
                    text += block["thinking"]
        total += max(estimate_text(text) + extra_tokens, _PER_MESSAGE_FLOOR)
    return total


__all__ = ["estimate_messages", "estimate_text"]
