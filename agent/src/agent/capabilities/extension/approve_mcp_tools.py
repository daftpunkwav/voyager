"""approve_mcp_tools capability: approve external MCP tools into the
conversation tool surface (package with names=['*'] or by name).

Cumulative (per-item or package "*") and remounts after approval; tools
leave only by removing the whole server. Effectively USER-only: the approval
list lives in the user_only setting agent.mcp.servers (see the parity
exception list).
"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ActorRef, ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="approve_mcp_tools",
        description="Approve external MCP tools into the conversation tool surface (package with names=['*'] or by name)",
        cost=1,
    )
    async def approve_mcp_tools(
        id: str, names: list[str] | None = None, _actor: ActorRef | None = None
    ) -> dict:
        cfg = deps.mcp.find_config(id)
        if cfg is None:
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND, f"no such external MCP: {id}")
        prev = list(cfg.get("approved") or [])
        if names is None:
            if cfg.get("approval") != "package":
                raise ServiceError(
                    "agent",
                    ErrorSuffix.INVALID_INPUT,
                    "per-item approval requires names; pass names=['*'] for package approval",
                )
            names = ["*"]
        if "*" in names or "*" in prev:
            approved = ["*"]  # keep package-level approval once granted; never silently narrow it
        else:
            remote_names = {t.get("name") for t in await deps.mcp.preview(id)}
            unknown = [n for n in names if n not in remote_names]
            if unknown:
                raise ServiceError(
                    "agent",
                    ErrorSuffix.INVALID_INPUT,
                    f"these tools are not in the preview: {', '.join(unknown)};"
                    "refresh the tool list first, then approve",
                )
            # Per-item approval is cumulative (never revokes prior approvals); revocation
            # happens only by removing the whole server.
            approved = sorted(set(prev) | set(names))
        await deps.mcp.upsert_config({**cfg, "approved": approved}, _actor)
        mounted = deps.mcp.remount(id, approved)
        return {
            "ok": True,
            "id": id,
            "approved": approved,
            "mounted": mounted,
            "note": "Approved tools enter the tool roster; the in-flight turn cannot see"
            " them — they become visible on the next message or in a new conversation.",
        }
