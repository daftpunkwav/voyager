"""todo_read tool: current plan with progress (binds read_plan; the human
capability of the same name binds the same function)."""

from __future__ import annotations

from typing import Any

from agent.tools.core.base import AgentTool
from agent.tools.workspace.todo_store import TodoStore, read_plan


def todo_read_tool(store: TodoStore) -> AgentTool:
    def todo_read() -> dict[str, Any]:
        return read_plan(store)

    return AgentTool(
        name="todo_read",
        description="读取当前任务计划与完成进度",
        handler=todo_read,
        concurrent_safe=True,
        schema={"type": "object", "properties": {}},
    )


__all__ = ["todo_read_tool"]
