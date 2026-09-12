"""cancel_job tool: cancel one background task (same capability as the
activity view's stop action; routed to the source domain)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def cancel_job_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "cancel_job",
        description="取消一个后台任务(按 list_jobs 的 id;路由到来源域自己的取消能力)",
        audit=audit,
        write=True,
    )


__all__ = ["cancel_job_tool"]
