"""preview_mcp_tools capability: list tools of a configured external MCP
again (preview works even when unapproved).

Read-only; the agent's preview_mcp_tools tool binds the same capability.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="preview_mcp_tools",
        description="List tools of a configured external MCP again (preview works even when unapproved)",
    )
    async def preview_mcp_tools(id: str) -> dict:
        preview = await deps.mcp.preview(id)  # raises AGENT.UNAVAILABLE with a readable message
        return {"id": id, "preview": preview}
