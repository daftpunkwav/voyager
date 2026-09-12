"""delete_profile tool: delete one user-profile key-value (same capability
as the settings page)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def delete_profile_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "delete_profile",
        description="删除一条用户画像键值(键不存在不报错)",
        audit=audit,
        write=True,
    )


__all__ = ["delete_profile_tool"]
