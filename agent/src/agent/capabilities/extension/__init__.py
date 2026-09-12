"""Extension capability group (plugins, external MCP, user hooks).
Zero-logic aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.extension.add_mcp_server import register as _add_mcp_server
from agent.capabilities.extension.approve_mcp_tools import register as _approve_mcp_tools
from agent.capabilities.extension.install_plugin import register as _install_plugin
from agent.capabilities.extension.list_mcp_servers import register as _list_mcp_servers
from agent.capabilities.extension.list_plugins import register as _list_plugins
from agent.capabilities.extension.list_user_hooks import register as _list_user_hooks
from agent.capabilities.extension.preview_mcp_tools import register as _preview_mcp_tools
from agent.capabilities.extension.reload_user_hooks import register as _reload_user_hooks
from agent.capabilities.extension.remove_mcp_server import register as _remove_mcp_server
from agent.capabilities.extension.set_plugin_approval import register as _set_plugin_approval
from agent.capabilities.extension.uninstall_plugin import register as _uninstall_plugin


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _list_mcp_servers(reg, deps)
    _add_mcp_server(reg, deps)
    _preview_mcp_tools(reg, deps)
    _approve_mcp_tools(reg, deps)
    _remove_mcp_server(reg, deps)
    _list_plugins(reg, deps)
    _set_plugin_approval(reg, deps)
    _install_plugin(reg, deps)
    _uninstall_plugin(reg, deps)
    _reload_user_hooks(reg, deps)
    _list_user_hooks(reg, deps)
