"""clear_memory capability: clear one memory zone.

`clear_memory()` is the one implementation; the capability and the agent's
clear_memory tool (L2 confirm) both bind it.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps
from agent.memory import Memory


def clear_memory(memory: Memory, zone: str) -> dict:
    return {"zone": zone, "cleared": memory.clear(zone)}


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="clear_memory",
        description="Clear a memory zone (zone: profile/episodic/semantic/working/all)",
        cost=2,
    )
    def _clear_memory(zone: str) -> dict:
        return clear_memory(deps.memory, zone)
