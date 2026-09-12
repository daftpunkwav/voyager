"""list_mcp_servers tool: external MCP configs and runtime state (same
capability as the settings page)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def list_mcp_servers_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "list_mcp_servers",
        description="列出外接 MCP 服务器配置与运行状态(连接/错误/预览/已挂载工具)",
        audit=audit,
        concurrent_safe=True,
    )


__all__ = ["list_mcp_servers_tool"]
