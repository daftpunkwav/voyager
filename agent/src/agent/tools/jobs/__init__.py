"""Jobs tool group: the agent's window onto background tasks. Zero-logic
aggregation (same capabilities the human activity view uses)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks
from agent.tools.jobs.cancel_job import cancel_job_tool
from agent.tools.jobs.list_jobs import list_jobs_tool


def jobs_tools(registry: Registry, audit: AuditSinks | None = None) -> dict[str, AgentTool]:
    tools = (list_jobs_tool(registry, audit), cancel_job_tool(registry, audit))
    return {t.name: t for t in tools}


__all__ = ["jobs_tools"]
