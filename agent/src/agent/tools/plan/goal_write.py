"""goal_write tool: the agent's only goal transitions — reporting done or
blocked. Creating, pausing and resuming goals is human-side (the
auto-continuation budget must stay under human control; parity list)."""

from __future__ import annotations

from typing import Any

from agent.master.goal import BLOCKED, DONE
from agent.runtime.current import current_instance
from agent.tools.core.base import AgentTool


def goal_write_tool(goals: Any) -> AgentTool:
    async def goal_write(status: str, note: str = "", session_id: str = "") -> str:
        if status not in (DONE, BLOCKED):
            return "[参数错误] 只能标记 done 或 blocked;创建/暂停/恢复目标由用户完成"
        inst = current_instance.get()
        session = session_id or (inst.session if inst is not None else "")
        goal = goals.set_status(session, status)
        if goal is None:
            return f"[未找到] 会话 {session or '(当前)'} 没有持久目标"
        detail = f"({note.strip()[:200]})" if note.strip() else ""
        return f"目标已标记为 {status}{detail}"

    return AgentTool(
        name="goal_write",
        description="汇报持久目标的进展:标记 done(完成)或 blocked(受阻,附原因);不能创建或恢复目标",
        handler=goal_write,
        dimension="none",
        write=True,
        schema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": [DONE, BLOCKED]},
                "note": {"type": "string", "description": "一句话说明(受阻原因等)"},
                "session_id": {"type": "string", "description": "目标会话(空 = 当前会话)"},
            },
            "required": ["status"],
        },
    )


__all__ = ["goal_write_tool"]
