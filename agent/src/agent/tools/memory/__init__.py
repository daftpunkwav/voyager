"""Memory tool group: the agent's own memory surface. Zero-logic
aggregation; recall binds the on-demand loader, the rest bind the agent
capability registry (same capabilities the settings page calls).
"""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks
from agent.tools.memory.clear_memory import clear_memory_tool
from agent.tools.memory.delete_profile import delete_profile_tool
from agent.tools.memory.get_memory import get_memory_tool
from agent.tools.memory.recall_memory import recall_memory_tool
from agent.tools.memory.set_profile import set_profile_tool


def memory_tools(registry: Registry, audit: AuditSinks | None = None) -> dict[str, AgentTool]:
    tools = (
        get_memory_tool(registry, audit),
        clear_memory_tool(registry, audit),
        set_profile_tool(registry, audit),
        delete_profile_tool(registry, audit),
    )
    return {t.name: t for t in tools}


__all__ = ["memory_tools", "recall_memory_tool"]
