"""todo_write tool: whole-list replacement of the agent's current plan."""

from __future__ import annotations

from typing import Any

from agent.tools.core.base import AgentTool
from agent.tools.workspace.todo_store import STATUSES, TodoStore, progress


def todo_write_tool(store: TodoStore) -> AgentTool:
    def todo_write(items: list[dict[str, Any]]) -> dict[str, Any]:
        saved = store.replace(items)
        return {"items": saved, **progress(saved)}

    return AgentTool(
        name="todo_write",
        description=(
            "写入当前任务计划(整表替换)。多步任务开头先列全部步骤,"
            "每完成一步把对应条目置 done,新发现的步骤追加为 pending;"
            "status: pending / in_progress / done"
        ),
        handler=todo_write,
        write=True,
        schema={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": list(STATUSES),
                            },
                        },
                        "required": ["content"],
                    },
                },
            },
            "required": ["items"],
        },
    )


__all__ = ["todo_write_tool"]
