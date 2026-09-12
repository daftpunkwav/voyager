"""goal_read tool: the session's durable goal and its status (read-only)."""

from __future__ import annotations

from typing import Any

from agent.runtime.current import current_instance
from agent.tools.core.base import AgentTool


def goal_read_tool(goals: Any) -> AgentTool:
    async def goal_read(session_id: str = "") -> dict | str:
        inst = current_instance.get()
        session = session_id or (inst.session if inst is not None else "")
        goal = goals.get(session)
        if goal is None:
            return f"会话 {session or '(当前)'} 没有持久目标"
        return {"session": session, "text": goal.text, "status": goal.status, "rounds": goal.rounds}

    return AgentTool(
        name="goal_read",
        description="读取当前会话的持久目标(文本、状态、今日续跑轮数)",
        handler=goal_read,
        dimension="none",
        concurrent_safe=True,
        schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "目标会话(空 = 当前会话)"}
            },
        },
    )


__all__ = ["goal_read_tool"]
