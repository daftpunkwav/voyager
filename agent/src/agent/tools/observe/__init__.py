"""Observe tool group: the agent reads its own operational state (events,
quota, tool roster). Zero-logic aggregation.

Deliberately absent: list_personas — the persona roster is resident in the
system prompt (frozen parity exception). Session search/trace live in the
aggregated session tool (tools/session/).
"""

from __future__ import annotations

from platform_capability import Registry
from platform_eventbus import EventLog

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks
from agent.tools.observe.describe_tool import describe_tool_tool
from agent.tools.observe.get_resource_quota import get_resource_quota_tool
from agent.tools.observe.list_tools import list_tools_tool
from agent.tools.observe.read_events import read_events_tool
from agent.tools.observe.search_tools import search_tools_tool


def observe_tools(
    registry: Registry, log: EventLog, audit: AuditSinks | None = None
) -> dict[str, AgentTool]:
    tools = (
        read_events_tool(log),
        get_resource_quota_tool(registry, audit),
        list_tools_tool(registry, audit),
        describe_tool_tool(registry, audit),
        search_tools_tool(registry, audit),
    )
    return {t.name: t for t in tools}


__all__ = ["observe_tools"]
