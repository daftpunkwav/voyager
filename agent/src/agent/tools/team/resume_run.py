"""resume_run tool: rebuild a task instance from a checkpoint and optionally
continue it in the background (same capability as the team page)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def resume_run_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "resume_run",
        description=(
            "从检查点恢复一个任务实例(仅任务态 REACT);continue_run=true 立即在后台续跑,"
            "否则保持 PAUSED 等待后续指令"
        ),
        audit=audit,
        write=True,
    )


__all__ = ["resume_run_tool"]
