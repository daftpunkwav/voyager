"""Observe tool group: the agent's operational self-observation (events,
quota) in one tool. Zero-logic aggregation; the tool binds the observe
capability (schema derived from it). Roster introspection (list / describe /
search) lives in the aggregated tools tool, not here."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks
from agent.tools.observe.observe import observe_tool


def observe_tools(registry: Registry, audit: AuditSinks | None = None) -> dict[str, AgentTool]:
    tool = observe_tool(registry, audit)
    return {tool.name: tool}


__all__ = ["observe_tools"]
