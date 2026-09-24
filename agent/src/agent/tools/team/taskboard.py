"""taskboard tool: the team's publish / claim / confirm board in one tool,
bound to the same-name capability (defaults resolve from the executing
instance's context: persona = claimant/publisher, session = current chat)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def taskboard_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "taskboard",
        description=(
            "团队任务板,action: "
            "publish(title,brief — 方案敲定后把任务发上板,brief 写清目标/约束/期望产出)/ "
            "claim(task_id,note — 认领任务,note 可留言商议:需要更多信息/手头任务太多)/ "
            "confirm(task_id — 发布者拍板确认,任务转入后台执行,过程在右侧智能体面板)/ "
            "list(session,status — 看板上任务)"
        ),
        audit=audit,
        write=True,
    )


__all__ = ["taskboard_tool"]
