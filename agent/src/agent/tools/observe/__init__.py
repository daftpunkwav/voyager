"""Observe tool group: the agent reads its own operational state (events,
quota, tool roster). Zero-logic aggregation.

Deliberately absent: list_personas — the persona roster is resident in the
system prompt (frozen parity exception).
"""

from __future__ import annotations

from typing import Any

from platform_capability import Registry
from platform_eventbus import EventLog

from agent.runtime.session_index import SessionIndex
from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks
from agent.tools.observe.get_resource_quota import get_resource_quota_tool
from agent.tools.observe.list_tools import list_tools_tool
from agent.tools.observe.read_events import read_events_tool
from agent.tools.observe.search_tools import search_tools_tool
from agent.tools.observe.session_search import session_search_tool
from agent.tools.observe.session_trace import session_trace_tool


def observe_tools(
    registry: Registry, log: EventLog, audit: AuditSinks | None = None
) -> dict[str, AgentTool]:
    tools = (
        read_events_tool(log),
        get_resource_quota_tool(registry, audit),
        list_tools_tool(registry, audit),
        search_tools_tool(registry, audit),
    )
    return {t.name: t for t in tools}


__all__ = ["observe_tools", "session_retrieval_tools"]


def session_retrieval_tools(index: SessionIndex, manager: Any) -> dict[str, AgentTool]:
    """Session search + lineage tools (agent-only; parity table)."""
    search = session_search_tool(index)
    trace = session_trace_tool(manager)
    return {search.name: search, trace.name: trace}
