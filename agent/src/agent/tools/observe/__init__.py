"""Observe tool group: the agent's operational self-observation (events,
quota) in one tool. Zero-logic aggregation; the tool binds the observe
capability (the roster tools moved into the aggregated tools tool)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks
from agent.tools.observe.observe import observe_tool


def observe_tools(registry: Registry, audit: AuditSinks | None = None) -> dict[str, AgentTool]:
    tool = observe_tool(registry, audit)
    return {tool.name: tool}


__all__ = ["observe_tools"]
