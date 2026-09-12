"""pause_run tool: cooperatively pause a running subagent (same capability
as the team page's pause action; audited as actor=agent)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def pause_run_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "pause_run",
        description="协作式暂停一个运行中的 subagent(在当前步骤完成后暂停并保存检查点;'chat' = 主对话实例)",
        audit=audit,
        write=True,
    )


__all__ = ["pause_run_tool"]
