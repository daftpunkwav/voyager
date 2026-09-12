"""read_board tool: read the task-scoped shared blackboard (defaults to the
calling instance's own task)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.runtime.current import current_instance
from agent.tools.core.base import AgentTool

if TYPE_CHECKING:
    # Type-only: a runtime import would pull agent.master (via its package
    # __init__) into the tool layer and make plain `import agent.subagent`
    # order-dependent (master.sessions reads agent.subagent back)
    from agent.master.blackboard import Blackboard


def read_board_tool(blackboard: Blackboard) -> AgentTool:
    def default_task() -> str:
        inst = current_instance.get()
        if inst is not None:
            return inst.task.goal[:80]
        return ""

    def read_board(task: str = "", limit: int = 20) -> list:
        return blackboard.read(task=task or default_task(), limit=limit)

    return AgentTool(
        name="read_board",
        description="读取共享黑板:同任务各 subagent 留下的便签(作者/内容/时间);了解协作分工与中间结论",
        handler=read_board,
        dimension="none",
        concurrent_safe=True,
        schema={
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "任务名(默认当前任务)"},
                "limit": {"type": "integer"},
            },
        },
    )


__all__ = ["read_board_tool"]
