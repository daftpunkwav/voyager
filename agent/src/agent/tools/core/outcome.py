"""Tool-call outcome: the structured result of one invocation.

ToolResult carries what the LLM needs (text) plus what operators and UIs
need (ok/title/metadata) in one value. Handlers may return str (legacy),
JSON-shaped dict/list (serialized as before), or ToolResult directly for
rich metadata; normalize() unifies them without changing the LLM-facing
text. Toolbelt.call() keeps returning plain text; call_detailed() exposes
the full outcome for tracing and UI layers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """One tool-call outcome.

    ok: False for pipeline rejections (unknown tool, denied, validation,
    failure) as well as handler errors; True only when the handler ran.
    text: the exact string handed to the LLM.
    title: short human label for progress UIs (defaults to the tool name).
    metadata: machine facts for tracing/UIs (truncated, totals, paths...);
    free-form per tool, never required.
    """

    name: str
    ok: bool
    text: str
    title: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def with_title(self, title: str) -> ToolResult:
        """Copy with a UI label; empty title falls back to the tool name."""
        return ToolResult(
            name=self.name,
            ok=self.ok,
            text=self.text,
            title=title or self.name,
            metadata=dict(self.metadata or {}),
        )


def normalize(name: str, raw: Any) -> ToolResult:
    """Unify a handler return into a ToolResult.

    str passes through untouched; ToolResult passes through with an empty
    title defaulted; anything else serializes exactly like the legacy path
    (json.dumps with ensure_ascii=False, str fallback).
    """
    if isinstance(raw, ToolResult):
        title = raw.title or name
        # metadata=None defended: a hand-built outcome must never crash the
        # pipeline with TypeError (it would fail the whole turn instead of
        # becoming a [工具失败] text result).
        return ToolResult(
            name=raw.name or name,
            ok=raw.ok,
            text=raw.text,
            title=title,
            metadata=dict(raw.metadata or {}),
        )
    if isinstance(raw, str):
        return ToolResult(name=name, ok=True, text=raw, title=name)
    return ToolResult(
        name=name,
        ok=True,
        text=json.dumps(raw, ensure_ascii=False, default=str),
        title=name,
    )


__all__ = ["ToolResult", "normalize"]
