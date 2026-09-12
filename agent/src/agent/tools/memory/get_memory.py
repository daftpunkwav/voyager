"""get_memory tool: memory snapshot (profile + recent episodic/semantic +
working count), same capability the settings page reads."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def get_memory_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "get_memory",
        description="查看自己的记忆快照:用户画像键值、最近情节/语义条目、工作记忆条数、保留期",
        audit=audit,
        concurrent_safe=True,
    )


__all__ = ["get_memory_tool"]
