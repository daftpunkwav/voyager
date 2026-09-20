"""Extension tool group: plugins, external MCP, user hooks in one tool —
the agent-side projection of the same extension capability the settings page
calls. Zero-logic aggregation.

Deliberately absent (frozen parity exceptions): set_plugin_approval,
add_mcp_server, approve_mcp_tools, remove_mcp_server — they write user_only
settings that gate the agent's own tool surface."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks
from agent.tools.extension.extension import extension_tool


def extension_tools(registry: Registry, audit: AuditSinks | None = None) -> dict[str, AgentTool]:
    tool = extension_tool(registry, audit)
    return {tool.name: tool}


__all__ = ["extension_tools"]
