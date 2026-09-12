"""clear_memory tool: clear one memory zone (irreversible, L2 confirm)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def clear_memory_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "clear_memory",
        description="清空某一记忆区(zone: profile/episodic/semantic/working/all;不可逆,需用户确认)",
        audit=audit,
        write=True,
        irreversible=True,
    )


__all__ = ["clear_memory_tool"]
