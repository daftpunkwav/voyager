"""list_jobs tool: the same background-task projection the capability
exposes (audited as actor=agent)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def list_jobs_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "list_jobs",
        description="查看后台任务(导入/索引/队列):id、类型、状态、时间;了解后台在忙什么",
        audit=audit,
        concurrent_safe=True,
    )


__all__ = ["list_jobs_tool"]
