"""remove_mcp_server capability: disconnect, unmount its tools, delete the
config.

Effectively USER-only: deletes from the user_only setting agent.mcp.servers
(see the parity exception list).
"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ActorRef, ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="remove_mcp_server",
        description="Remove an external MCP: disconnect, unmount its tools, delete the config",
        cost=1,
    )
    async def remove_mcp_server(id: str, _actor: ActorRef | None = None) -> dict:
        if deps.mcp.find_config(id) is None:
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND, f"no such external MCP: {id}")
        deps.mcp.unmount(id)
        await deps.mcp.drop_session(id)
        await deps.mcp.delete_config(id, _actor)
        return {"ok": True, "id": id}
