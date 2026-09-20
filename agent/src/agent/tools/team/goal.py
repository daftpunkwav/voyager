"""goal tool: the durable session goal in one tool — get / set / status,
bound to the same goal capability (the actor-based driver rules live there:
the agent reports done/blocked and owns sub goals; the main goal's text and
active/paused state belong to the user)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def goal_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "goal",
        description=(
            "持久目标,action: get(返回 {main, subs} 全量快照)/"
            " set(scope=sub 增删改副目标,index 省略=追加,text 空=删除;"
            "scope=main 改主目标文本仅限用户)/"
            " status(主目标:agent 只能报 done/blocked;副目标:pending/doing/done/blocked)"
        ),
        audit=audit,
        write=True,
    )


__all__ = ["goal_tool"]
