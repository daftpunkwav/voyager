"""get_memory capability: memory snapshot (profile + recent episodic/semantic
+ working count) with lazy retention purge.

`get_memory()` is the one implementation; the capability and the agent's
get_memory tool both bind it.
"""

from __future__ import annotations

from typing import Any

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps
from agent.memory import Memory


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
        name="get_memory",
        description="Memory snapshot: profile summary + key-values, recent episodic/semantic items, working-memory count",
    )
    def _get_memory() -> dict:
        return get_memory(deps.memory, deps.settings)
