"""write_board tool: leave a short note on the task-scoped shared blackboard
for sibling subagents (L1; cards are capped)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.runtime.current import current_instance
from agent.tools.core.base import AgentTool

if TYPE_CHECKING:
    # Type-only: a runtime import would pull agent.master (via its package
    # __init__) into the tool layer and make plain `import agent.subagent`
    # order-dependent (master.sessions reads agent.subagent back)
    from agent.master.blackboard import Blackboard


def write_board_tool(blackboard: Blackboard) -> AgentTool:
    def default_author() -> str:
        inst = current_instance.get()
        return inst.name if inst is not None else "chat"

    def default_task() -> str:
        inst = current_instance.get()
        return inst.task.goal[:80] if inst is not None else ""

    def write_board(text: str, task: str = "", author: str = "") -> dict:
        return blackboard.write(
            task=task or default_task(),
            text=text,
            author=author or default_author(),
        )

    return AgentTool(
        name="write_board",
        description="在共享黑板留一张便签(≤500 字):分工、关键发现、中间结论,供同任务其他 subagent 读取",
        handler=write_board,
        dimension="app",
        write=True,
        schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "task": {"type": "string", "description": "任务名(默认当前任务)"},
                "author": {"type": "string", "description": "署名(默认当前实例名)"},
            },
            "required": ["text"],
        },
    )


__all__ = ["write_board_tool"]
