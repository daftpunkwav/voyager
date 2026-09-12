"""add_mcp_server capability: add an external MCP server (validate and
persist first, then try connecting for a preview).

Effectively USER-only: the config lives in the user_only setting
agent.mcp.servers (an MCP server adds executables/tools to the agent's own
surface — a privilege-escalation boundary); an agent actor is rejected by the
settings layer. Listed in the parity exception list.
"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ActorRef, ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.clients.pool import validate_server_config


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="add_mcp_server",
        description="Add an external MCP server (stdio command or HTTP URL);"
        " validate and persist first, then try connecting for a preview",
        cost=1,
    )
    async def add_mcp_server(
        id: str,
        kind: str,
        name: str = "",
        command: str = "",
        args: list[str] | None = None,
        url: str = "",
        approval: str = "item",
        _actor: ActorRef | None = None,
    ) -> dict:
        cfg = validate_server_config(
            {
                "id": id,
                "kind": kind,
                "name": name,
                "command": command,
                "args": args or [],
                "url": url,
                "approval": approval,
            }
        )
        if deps.mcp.find_config(cfg["id"]) is not None:
            raise ServiceError(
                "agent",
                ErrorSuffix.CONFLICT,
                f"an external MCP with the same id already exists: {cfg['id']}",
            )
        await deps.mcp.upsert_config({**cfg, "approved": []}, _actor)
        try:
            preview = await deps.mcp.preview(cfg["id"])
        except ServiceError as exc:
            # Keep the config even if the connection fails: the user can fix the
            # environment and retry via "refresh tool list"; never drop a half-added config.
            return {
                "ok": True,
                "id": cfg["id"],
                "connected": False,
                "error": str(exc),
                "preview": [],
            }
        return {"ok": True, "id": cfg["id"], "connected": True, "error": "", "preview": preview}
