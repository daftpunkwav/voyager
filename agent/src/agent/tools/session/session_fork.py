"""session_fork tool: fork a session (default: the active one) into a new
session carrying a copy of its history."""

from __future__ import annotations

from typing import Any

from agent.tools.core.base import AgentTool

SessionManagerLike = Any  # agent.master.sessions.SessionManager (duck-typed)


def session_fork_tool(manager: SessionManagerLike) -> AgentTool:
    async def session_fork(source_session_id: str = "", title: str = "") -> dict:
        """Fork an existing session (default: the active one) into a new
        session carrying a copy of its history."""
        return manager.fork(source_session_id, title=title.strip()[:40])

    return AgentTool(
        name="session_fork",
        description="把某个会话(默认当前会话)的上下文复制为一个新会话,用于开辟旁路讨论而不污染原会话",
        handler=session_fork,
        dimension="none",
    )


__all__ = ["session_fork_tool"]
