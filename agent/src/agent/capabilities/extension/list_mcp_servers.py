"""list_mcp_servers capability: external MCP configs and runtime state.

Read-only; the agent's list_mcp_servers tool binds the same capability.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="list_mcp_servers",
        description="External MCP configs and runtime state (connection/error/preview/mounted)",
    )
    def list_mcp_servers() -> list[dict]:
        return deps.mcp.list_state()
