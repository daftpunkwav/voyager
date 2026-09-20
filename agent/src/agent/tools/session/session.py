"""session tool: the agent's whole chat-session surface in one tool —
list/create/fork/rename/delete/get/read/search/trace/pin/archive, with
set_active refused by the surface guard (human-only, interaction integrity).

Same name and same action dispatch as the human REST capability — both bind
session_action() (one implementation, two drivers). The tool runs the
capability through the execute guard chain (audit symmetry), so deletes and
forks land in the same audit log with actor=agent.
"""

from __future__ import annotations

from typing import Any

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool
from agent.tools.session.actions import ACTION_TABLE, SessionManagerLike, agent_surface_guard


def session_tool(
    registry: Registry,
    sessions: SessionManagerLike,
    index: Any = None,
    log: Any = None,
    audit: AuditSinks | None = None,
) -> AgentTool:
    def _guard(args: dict[str, Any]) -> str | None:
        return agent_surface_guard(sessions, args)

    return capability_tool(
        registry,
        "session",
        description="管理聊天会话,action: "
        + ACTION_TABLE
        + ";不能变更用户正在看的会话(set_active 人类专属,rename/delete 当前会话会被拒绝)",
        audit=audit,
        write=True,
        guard=_guard,
    )


__all__ = ["session_tool"]
