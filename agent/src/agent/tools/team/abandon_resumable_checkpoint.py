"""abandon_resumable_checkpoint tool: delete a checkpoint from disk and stop
its in-memory instance (irreversible, L2 confirm)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def abandon_resumable_checkpoint_tool(
    registry: Registry, audit: AuditSinks | None = None
) -> AgentTool:
    return capability_tool(
        registry,
        "abandon_resumable_checkpoint",
        description="放弃一个可恢复检查点(从磁盘删除并停止内存实例;不可逆,需用户确认)",
        audit=audit,
        write=True,
        irreversible=True,
    )


__all__ = ["abandon_resumable_checkpoint_tool"]
