"""Memory tool group: the agent's whole memory surface in one tool. Zero-logic
aggregation; the tool binds the agent capability registry (the same memory
capability the settings page calls, audit symmetry)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks
from agent.tools.memory.memory import memory_tool


def memory_tools(registry: Registry, audit: AuditSinks | None = None) -> dict[str, AgentTool]:
    tool = memory_tool(registry, audit)
    return {tool.name: tool}


__all__ = ["memory_tools"]
