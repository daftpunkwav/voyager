"""board tool: the task-shared blackboard in one tool — read / write, bound
to the same board capability (defaults resolve from the executing instance's
context)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def board_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "board",
        description=(
            "共享黑板,action: read(task,limit,读同任务各 subagent 的便签:"
            "作者/内容/时间,了解协作分工与中间结论)/"
            " write(text ≤500 字,留便签:分工、关键发现、中间结论;"
            "task 默认当前任务,author 默认当前实例名)"
        ),
        audit=audit,
        write=True,
    )


__all__ = ["board_tool"]
