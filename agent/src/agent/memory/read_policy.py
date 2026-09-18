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
import time
from typing import Any

from agent.memory import Memory

HEADER = "【相关记忆】"

#: Surfaced once at the end when any hit carries real age: models are poor at
#: date arithmetic — "47天前" triggers staleness reasoning a raw ts never will.
STALE_NOTE = "注:记忆是当时快照,可能已过时,以当前实际状态为准。"

_FALLBACK_CHARS = 120

_DAY_S = 86400.0


def _age_suffix(hit: dict[str, Any]) -> str:
    """ "(N天前)" for hits that carry a timestamp; empty for fresh/undated ones."""
    ts = hit.get("ts") or hit.get("created_at")
    try:
        ts = float(ts)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    if ts <= 0:
        return ""
    days = int((time.time() - ts) // _DAY_S)
    return f"({days}天前)" if days >= 1 else ""


def _line(hit: dict[str, Any]) -> str:
    """One compact line per hit; the source label tells the model which store
    answered (profile key / episode kind / fact triple / vector match)."""
    source = str(hit.get("from") or "")
    age = _age_suffix(hit)
    if source == "profile":
        return f"[画像] {hit.get('key', '')}: {hit.get('value', '')}".strip()
    if source == "episodic":
        return f"[{hit.get('kind', '')}] {hit.get('summary', '')}{age}".strip()
    if source == "semantic":
        return (
            f"[事实] {hit.get('subject', '')} {hit.get('relation', '')} "
            f"{hit.get('object', '')}{age}"
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
    any_aged = False
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
        if _age_suffix(hit):
            any_aged = True
    if any_aged:
        lines.append(STALE_NOTE)
    while lines and sum(len(line) + 1 for line in lines) > max_chars:
        lines.pop()
    if not lines:
        return ""
    return HEADER + "\n" + "\n".join(lines)


__all__ = ["HEADER", "render_relevant_recall"]
