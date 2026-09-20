"""memory capability: the human REST surface for the memory domain — one
action parameter covers query/recall/remember/forget/clear.

Same name and same action dispatch as the agent's memory tool — both bind
memory_action() (one implementation, two drivers). The settings page's
snapshot (query) keeps its lazy retention purge; recall stays bounded by the
clamp so one call cannot pull an unbounded result set.
"""

from __future__ import annotations

from typing import Any

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.memory import Memory

#: Recall bounds (from the former recall_memory tool).
_RECALL_DEFAULT = 8
_RECALL_MAX = 20
_RECALL_MIN = 1


def memory_action(
    memory: Memory,
    settings: Any,
    *,
    action: str,
    query: str = "",
    limit: int = _RECALL_DEFAULT,
    key: str = "",
    value: str = "",
    zone: str = "",
) -> dict | list:
    """Dispatch one memory action against the shared Memory store."""
    if action == "query":
        return get_memory(memory, settings)
    if action == "recall":
        needle = str(query or "").strip()
        if not needle:
            raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "query must not be empty")
        count = limit if isinstance(limit, int) and not isinstance(limit, bool) else _RECALL_DEFAULT
        return memory.recall(needle, max(_RECALL_MIN, min(count, _RECALL_MAX)))
    if action == "remember":
        cleaned = (key or "").strip()
        if not cleaned:
            raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "profile key must not be empty")
        memory.profile.set(cleaned, value)
        return {"key": cleaned, "ok": True}
    if action == "forget":
        cleaned = (key or "").strip()
        if not cleaned:
            raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "profile key must not be empty")
        memory.profile.delete(cleaned)
        return {"key": cleaned, "ok": True}
    if action == "clear":
        return {"zone": zone, "cleared": memory.clear(zone)}
    raise ServiceError(
        "agent",
        ErrorSuffix.INVALID_INPUT,
        f"unknown action: {action!r}",
        hint="valid actions: query/recall/remember/forget/clear",
    )


def get_memory(memory: Memory, settings: Any) -> dict:
    """Settings-page data source: reads retention_days and lazily purges
    expired episodic/semantic facts (same spirit as the notes trash bin)."""
    retention = int(settings.get("agent.memory.retention_days") or 0)
    purged = memory.purge(retention)
    episodic_recent = memory.episodic.recent(limit=20)
    semantic_recent = memory.semantic.query(limit=20)
    return {
        "profile": {
            "summary": memory.profile.render(),
            "items": [{"key": k, "value": v} for k, v in memory.profile.all().items()],
        },
        "episodic": {"recent": episodic_recent, "shown": len(episodic_recent)},
        "semantic": {"recent": semantic_recent, "shown": len(semantic_recent)},
        "working": {"size": len(memory.working)},
        "retention_days": retention,
        "purged_episodic": purged["episodic"],
        "purged_semantic": purged.get("semantic", 0),
        "vector_recall": memory.vector_status(),
    }


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="memory",
        description=(
            "Memory domain: action query (snapshot: profile/episodic/semantic/working/"
            "retention), recall (query,limit), remember (key,value), forget (key), "
            "clear (zone: profile/episodic/semantic/working/all)"
        ),
    )
    def memory(
        action: str,
        query: str = "",
        limit: int = _RECALL_DEFAULT,
        key: str = "",
        value: str = "",
        zone: str = "",
    ) -> dict | list:
        return memory_action(
            deps.memory,
            deps.settings,
            action=action,
            query=query,
            limit=limit,
            key=key,
            value=value,
            zone=zone,
        )
