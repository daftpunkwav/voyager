"""list_plugins tool: plugin inventory with approval state (same capability
as the settings page)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def list_plugins_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "list_plugins",
        description="列出插件清单(已发现/已批准/包含的 skill、hook、MCP 明细;未批准的插件不会加载)",
        audit=audit,
        concurrent_safe=True,
    )


__all__ = ["list_plugins_tool"]
