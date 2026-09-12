"""session_list tool: all chat sessions, most recent first (binds the
SessionManager the human session_list capability also drives)."""

from __future__ import annotations

from typing import Any

from agent.tools.core.base import AgentTool

SessionManagerLike = Any  # agent.master.sessions.SessionManager (duck-typed)


def session_list_tool(manager: SessionManagerLike) -> AgentTool:
    async def session_list() -> dict:
        """All chat sessions, most recent first."""
        rows = manager.list()
        return {"sessions": rows, "active": manager.active_id()}

    return AgentTool(
        name="session_list",
        description="列出用户的全部聊天会话(id/标题/状态),当前会话用 session 字段标注",
        handler=session_list,
        dimension="none",
        concurrent_safe=True,
    )


__all__ = ["session_list_tool"]
