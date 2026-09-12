"""rename_session tool: rename a chat session other than the one the user
is looking at (same capability as the session list; audited as agent).

Agent-side precondition (D-01): the active session is refused so the
conversation the user is in never changes under them.
"""

from __future__ import annotations

from typing import Any

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool

SessionManagerLike = Any  # agent.master.sessions.SessionManager (duck-typed)


def rename_session_tool(
    registry: Registry, manager: SessionManagerLike, audit: AuditSinks | None = None
) -> AgentTool:
    def _not_active(args: dict[str, Any]) -> str | None:
        if str(args.get("session_id") or "") == str(manager.active_id() or ""):
            return "[已拒绝] 不能重命名用户当前正在看的会话;请让用户自己操作,或先 session_create 再处理"
        return None

    return capability_tool(
        registry,
        "rename_session",
        description="重命名一个非当前会话(用户正在看的会话不可改;标题截断 40 字)",
        audit=audit,
        write=True,
        guard=_not_active,
    )


__all__ = ["rename_session_tool"]
