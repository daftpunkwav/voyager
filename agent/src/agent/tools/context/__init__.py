"""Context tool group: LLM-driven context management (status + compaction).
Zero-logic aggregation of the per-tool factories.
"""

from __future__ import annotations

from agent.tools.context.compact_context import compact_context_tool
from agent.tools.context.context_status import context_status_tool
from agent.tools.core.base import AgentTool


def context_tools() -> dict[str, AgentTool]:
    tools = (context_status_tool(), compact_context_tool())
    return {t.name: t for t in tools}


__all__ = ["context_tools"]
