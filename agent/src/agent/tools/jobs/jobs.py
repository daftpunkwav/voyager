"""jobs tool: background tasks in one tool — list / reorder / cancel, bound
to the same jobs capability the activity view drives (audit symmetry)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def jobs_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "jobs",
        description=(
            "后台任务:action list(limit,查看导入/索引/队列任务)/"
            " reorder(job_id,priority,数值小先跑)/ cancel(job_id,取消任务)"
        ),
        audit=audit,
        write=True,
    )


__all__ = ["jobs_tool"]
