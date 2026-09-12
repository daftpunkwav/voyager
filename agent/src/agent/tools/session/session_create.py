"""session_create tool: create a fresh empty session (the user's active
session is NOT switched)."""

from __future__ import annotations

from typing import Any

from agent.tools.core.base import AgentTool

SessionManagerLike = Any  # agent.master.sessions.SessionManager (duck-typed)


def session_create_tool(manager: SessionManagerLike) -> AgentTool:
    async def session_create(title: str = "") -> dict:
        """Create a fresh empty session (the user's active session is NOT
        switched; tell the user the new session id)."""
        return manager.create(title=title.strip()[:40])

    return AgentTool(
        name="session_create",
        description="新建一个空的聊天会话(不会切换用户当前会话);返回新会话 id,告知用户切换方式",
        handler=session_create,
        dimension="none",
    )


__all__ = ["session_create_tool"]
