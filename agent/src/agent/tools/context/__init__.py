"""Context tool group: the aggregated context surface (status / compact).
Zero-logic aggregation."""

from __future__ import annotations

from agent.tools.context.context import context_tool
from agent.tools.core.base import AgentTool


def context_tools() -> dict[str, AgentTool]:
    tool = context_tool()
    return {tool.name: tool}


__all__ = ["context_tools"]
