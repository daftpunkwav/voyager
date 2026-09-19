"""todowrite tool: the plan's single entry point. One action parameter covers
the whole lifecycle — set (whole-list replacement), query, update (patch one
entry by index), delete (one entry by index, or clear the list without one).

Same name, same operation as the human-side todowrite capability — both bind
plan_action() in todo_store (one implementation, two drivers). Handler-side
translation only: ServiceError becomes model-readable failure text. The plan
is per chat session: the executing turn's session picks the file; session-less
work (REPL, background runs) shares the global one.
"""

from __future__ import annotations

from typing import Any

from platform_contracts import ServiceError

from agent.runtime.current import current_session
from agent.tools.core.base import AgentTool
from agent.tools.workspace.todo_store import STATUSES, TodoStore, plan_action


def todowrite_tool(store: TodoStore) -> AgentTool:
    def todowrite(
        action: str = "query",
        items: list[dict[str, Any]] | None = None,
        index: int | None = None,
        content: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any] | str:
        plan = store.for_session(current_session())
        try:
            return plan_action(
                plan, action=action, items=items, index=index, content=content, status=status
            )
        except ServiceError as exc:
            hint = f";{exc.body.hint}" if exc.body.hint else ""
            return f"[参数错误] {exc.body.message}{hint}"

    return AgentTool(
        name="todowrite",
        description=(
            "管理当前任务计划(整表替换/查询/逐条更新/删除)。多步任务开头先 set 全部步骤,"
            "每完成一步 update 对应条目 status 为 done,新发现的步骤 update 追加或重新 set;"
            "action: set(整表替换,配 items)/ query(查当前计划)/"
            " update(按 index 改 content 或 status)/ delete(按 index 删单条,省略 index 清空);"
            "status: pending / in_progress / done"
        ),
        handler=todowrite,
        write=True,
        schema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["set", "query", "update", "delete"],
                    "description": "set 整表替换 / query 查询 / update 改单条 / delete 删单条或清空",
                },
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
                    "description": "set 时的完整计划(set 空表 = 清空)",
                },
                "index": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "update/delete 的目标条目(0 起始)",
                },
                "content": {"type": "string", "description": "update:新的条目内容"},
                "status": {
                    "type": "string",
                    "enum": list(STATUSES),
                    "description": "update:新的条目状态",
                },
            },
            "required": ["action"],
        },
    )


__all__ = ["todowrite_tool"]
