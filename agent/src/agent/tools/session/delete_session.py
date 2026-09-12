"""delete_session tool: delete a chat session other than the active one
(irreversible, L2 confirm; same capability as the session list).

Agent-side precondition (D-01): the active session is refused — removing
the conversation the user is in breaks the conversational contract.
"""

from __future__ import annotations

from typing import Any

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool

SessionManagerLike = Any  # agent.master.sessions.SessionManager (duck-typed)


def delete_session_tool(
    registry: Registry, manager: SessionManagerLike, audit: AuditSinks | None = None
) -> AgentTool:
    def _not_active(args: dict[str, Any]) -> str | None:
        if str(args.get("session_id") or "") == str(manager.active_id() or ""):
            return "[已拒绝] 不能删除用户当前正在看的会话;请让用户自己操作"
        return None

    return capability_tool(
        registry,
        "delete_session",
        description="删除一个非当前会话(运行中的会话会被拒绝;不可逆,需用户确认)",
        audit=audit,
        write=True,
        irreversible=True,
        guard=_not_active,
    )


__all__ = ["delete_session_tool"]
