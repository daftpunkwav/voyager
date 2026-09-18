"""delete_subagent capability: remove a user-built subagent definition.

`delete_subagent()` is the one implementation; the capability binds it.
Already-dispatched instances are unaffected: they carry their own trimmed
toolbelt, so removal only stops future dispatches by that name.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps
from agent.subagent.registry import SubagentRegistry


def delete_subagent(registry: SubagentRegistry, *, name: str) -> dict:
    """Delete a registered definition; unknown names raise AGENT.NOT_FOUND
    instead of reporting success for a no-op (mirrors SubagentRegistry.load)."""
    registry.load(name)  # existence check: raises NOT_FOUND for unknown names
    registry.delete(name)
    return {"deleted": name}


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="delete_subagent",
        description="Delete a user-built subagent definition (running instances are unaffected)",
    )
    def _delete_subagent(name: str) -> dict:
        return delete_subagent(deps.subagents, name=name)
