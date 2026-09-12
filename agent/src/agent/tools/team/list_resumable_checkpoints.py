"""list_resumable_checkpoints tool: checkpoints that can be resumed or must
be cleaned up after a restart (same capability as the team page)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def list_resumable_checkpoints_tool(
    registry: Registry, audit: AuditSinks | None = None
) -> AgentTool:
    return capability_tool(
        registry,
        "list_resumable_checkpoints",
        description="列出可恢复/待清理的任务检查点(run_id/状态/目标/是否可续跑)",
        audit=audit,
        concurrent_safe=True,
    )


__all__ = ["list_resumable_checkpoints_tool"]
