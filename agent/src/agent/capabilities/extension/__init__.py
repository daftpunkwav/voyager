"""Extension capability group (plugins, external MCP, user hooks).
Zero-logic aggregation: import each capability file and register it.

Deliberately separate (privileged boundaries, frozen parity exceptions):
set_plugin_approval / add_mcp_server / approve_mcp_tools / remove_mcp_server
write user_only settings that gate the agent's own tool surface."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.extension.add_mcp_server import register as _add_mcp_server
from agent.capabilities.extension.approve_mcp_tools import register as _approve_mcp_tools
from agent.capabilities.extension.extension import register as _extension
from agent.capabilities.extension.remove_mcp_server import register as _remove_mcp_server
from agent.capabilities.extension.set_plugin_approval import register as _set_plugin_approval


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _extension(reg, deps)
    _add_mcp_server(reg, deps)
    _approve_mcp_tools(reg, deps)
    _remove_mcp_server(reg, deps)
    _set_plugin_approval(reg, deps)
