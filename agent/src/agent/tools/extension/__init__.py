"""Extension tool group: plugins, external MCP, user hooks — the agent-side
projection of the same capabilities the settings page calls. Zero-logic
aggregation.

Deliberately absent (frozen parity exceptions): set_plugin_approval,
add_mcp_server, approve_mcp_tools, remove_mcp_server — they write user_only
settings that gate the agent's own tool surface.
"""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks
from agent.tools.extension.install_plugin import install_plugin_tool
from agent.tools.extension.list_mcp_servers import list_mcp_servers_tool
from agent.tools.extension.list_plugins import list_plugins_tool
from agent.tools.extension.list_user_hooks import list_user_hooks_tool
from agent.tools.extension.preview_mcp_tools import preview_mcp_tools_tool
from agent.tools.extension.reload_user_hooks import reload_user_hooks_tool
from agent.tools.extension.uninstall_plugin import uninstall_plugin_tool


def extension_tools(registry: Registry, audit: AuditSinks | None = None) -> dict[str, AgentTool]:
    tools = (
        list_plugins_tool(registry, audit),
        install_plugin_tool(registry, audit),
        uninstall_plugin_tool(registry, audit),
        list_mcp_servers_tool(registry, audit),
        preview_mcp_tools_tool(registry, audit),
        reload_user_hooks_tool(registry, audit),
        list_user_hooks_tool(registry, audit),
    )
    return {t.name: t for t in tools}


__all__ = ["extension_tools"]
