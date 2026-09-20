"""Tools tool group (the aggregated tools surface). Zero-logic aggregation."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks
from agent.tools.tools.tools import tools_tool


def tools_tools(registry: Registry, audit: AuditSinks | None = None) -> dict[str, AgentTool]:
    tool = tools_tool(registry, audit)
    return {tool.name: tool}


__all__ = ["tools_tools"]
