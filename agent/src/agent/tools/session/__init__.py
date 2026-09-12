"""Session tool group: the agent's chat-session surface. Zero-logic
aggregation; list/create/fork bind the SessionManager directly, rename and
delete bind the agent capability registry (non-active sessions only),
read_history pages the shared event log.

Registration happens in build_agent after the master exists (the tools bind
its public surface directly), not in the early tool-source merge.
"""

from __future__ import annotations

from typing import Any

from platform_capability import Registry
from platform_eventbus import EventLog

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks
from agent.tools.session.delete_session import delete_session_tool
from agent.tools.session.read_history import read_history_tool
from agent.tools.session.rename_session import rename_session_tool
from agent.tools.session.session_create import session_create_tool
from agent.tools.session.session_fork import session_fork_tool
from agent.tools.session.session_list import session_list_tool

SessionManagerLike = Any  # agent.master.sessions.SessionManager (duck-typed)


def session_tools(manager: SessionManagerLike) -> dict[str, AgentTool]:
    tools = (
        session_list_tool(manager),
        session_create_tool(manager),
        session_fork_tool(manager),
    )
    return {t.name: t for t in tools}


def session_governance_tools(
    registry: Registry,
    manager: SessionManagerLike,
    log: EventLog,
    audit: AuditSinks | None = None,
) -> dict[str, AgentTool]:
    tools = (
        rename_session_tool(registry, manager, audit),
        delete_session_tool(registry, manager, audit),
        read_history_tool(log, manager),
    )
    return {t.name: t for t in tools}


__all__ = ["session_governance_tools", "session_tools"]
