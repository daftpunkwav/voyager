"""list_plugins capability: plugin inventory (discovery + approval state).

Read-only for any authenticated actor; the agent's list_plugins tool binds
the same capability.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="list_plugins",
        description="Plugin inventory (discovery + approval state + contains counts and"
        " skill/hook/MCP details; unapproved plugins stay unloaded)",
    )
    def list_plugins() -> dict:
        return {"items": deps.plugins.list()}
