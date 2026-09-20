"""Jobs tool group: the agent's window onto background tasks in one tool.
Zero-logic aggregation (same capability the human activity view uses)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks
from agent.tools.jobs.jobs import jobs_tool


def jobs_tools(registry: Registry, audit: AuditSinks | None = None) -> dict[str, AgentTool]:
    tool = jobs_tool(registry, audit)
    return {tool.name: tool}


__all__ = ["jobs_tools"]
