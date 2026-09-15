"""Memory read policy: the resident relevance layer.

recall_memory is model-initiated - the model must think of asking. This
module makes the ask unnecessary for the common case: at each turn start
the system prompt carries the memory hits most relevant to the current
input, selected through the same recall facade the tool uses (profile +
episodic + semantic, optionally the vector channel). Long-term knowledge
stops depending on the model remembering to call recall.

Rendering is content-addressed: the same query renders the same bytes, so
an unchanged turn keeps the provider prefix cache stable. Episodic entries
already shown by the resident recent-cards layer are excluded, not
duplicated; profile hits whose key already rides the resident profile layer
are excluded the same way via exclude_profile_keys. The graph-side join
(semantic.node_id) stays out of scope: this module only reads the agent's
own memory stores.
"""

from __future__ import annotations

import json
from typing import Any

from agent.memory import Memory

HEADER = "【相关记忆】"

_FALLBACK_CHARS = 120


def _line(hit: dict[str, Any]) -> str:
    """One compact line per hit; the source label tells the model which store
    answered (profile key / episode kind / fact triple / vector match)."""
    source = str(hit.get("from") or "")
    if source == "profile":
        return f"[画像] {hit.get('key', '')}: {hit.get('value', '')}".strip()
    if source == "episodic":
        return f"[{hit.get('kind', '')}] {hit.get('summary', '')}".strip()
    if source == "semantic":
        return (
            f"[事实] {hit.get('subject', '')} {hit.get('relation', '')} {hit.get('object', '')}"
        ).strip()
    # Vector-channel hits (or future sources): keep the identity text bounded
    try:
        body = json.dumps(hit, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        body = str(hit)
    return f"[{source or 'memory'}] {body[:_FALLBACK_CHARS]}".strip()


def render_relevant_recall(
    memory: Memory,
    query: str,
    *,
    limit: int = 4,
    max_chars: int = 600,
    exclude_summaries: set[str] | None = None,
    exclude_profile_keys: set[str] | None = None,
) -> str:
    """The bounded relevance layer for the system prompt ("" when nothing
    scores). Hits come from Memory.recall; episodic entries whose summary is
    already on a resident card are skipped, as are profile hits whose key is
    already on the resident profile layer; the layer is trimmed
    oldest-hit-first to the character cap."""
    if limit <= 0 or max_chars <= 0 or not query.strip():
        return ""
    try:
        hits = memory.recall(query.strip(), limit=limit)
    except Exception:  # noqa: BLE001  # a broken memory store must never break the turn
        return ""
    exclude = exclude_summaries or set()
    excluded_keys = exclude_profile_keys or set()
    lines: list[str] = []
    seen: set[str] = set()
    for hit in hits:
        if str(hit.get("from")) == "episodic" and str(hit.get("summary") or "") in exclude:
            continue
        if str(hit.get("from")) == "profile" and str(hit.get("key") or "") in excluded_keys:
            continue
        line = _line(hit)
        if not line or line in seen:
            continue
        seen.add(line)
        lines.append(line)
    while lines and sum(len(line) + 1 for line in lines) > max_chars:
        lines.pop()
    if not lines:
        return ""
    return HEADER + "\n" + "\n".join(lines)


__all__ = ["HEADER", "render_relevant_recall"]
