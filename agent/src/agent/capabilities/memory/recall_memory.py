"""recall_memory capability: search agent memory (profile/episodic/semantic).

The agent's recall_memory tool binds the same Memory.recall.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg, name="recall_memory", description="Search agent memory (profile/episodic/semantic)"
    )
    def recall_memory(query: str, limit: int = 8) -> list[dict]:
        return deps.memory.recall(query, limit)
