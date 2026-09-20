"""Session tool group: the agent's chat-session surface. Zero-logic
aggregation; the one session tool binds the agent capability registry (the
human session capability is the same name/action dispatch), so registration
happens in build_agent after the registry exists.
"""

from __future__ import annotations

from platform_capability import Registry
from platform_eventbus import EventLog

from agent.runtime.session_index import SessionIndex
from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks
from agent.tools.session.actions import SessionManagerLike
from agent.tools.session.session import session_tool


def session_tools(
    registry: Registry,
    sessions: SessionManagerLike,
    index: SessionIndex | None = None,
    log: EventLog | None = None,
    audit: AuditSinks | None = None,
) -> dict[str, AgentTool]:
    tool = session_tool(registry, sessions, index, log, audit)
    return {tool.name: tool}


__all__ = ["session_tools"]
