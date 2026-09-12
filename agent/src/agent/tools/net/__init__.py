"""Network tool group: web_fetch / web_search (through the network
permission layer). Zero-logic aggregation of the per-tool factories.
"""

from __future__ import annotations

from agent.policy import PolicyEngine
from agent.tools.core.base import AgentTool
from agent.tools.net.web_fetch import web_fetch_tool
from agent.tools.net.web_search import web_search_tool


def web_tools(policy: PolicyEngine | None = None) -> dict[str, AgentTool]:
    tools = (web_fetch_tool(policy), web_search_tool(policy))
    return {t.name: t for t in tools}


__all__ = ["web_tools"]
