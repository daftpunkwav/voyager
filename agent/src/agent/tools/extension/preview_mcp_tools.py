"""preview_mcp_tools tool: list tools of a configured external MCP (works
even when unapproved; same capability as the settings page)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def preview_mcp_tools_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "preview_mcp_tools",
        description="预览某个已配置外接 MCP 提供的工具列表(未批准也可预览;批准只能由用户完成)",
        audit=audit,
        concurrent_safe=True,
    )


__all__ = ["preview_mcp_tools_tool"]
