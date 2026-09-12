"""set_profile tool: write/update one user-profile key-value (same
capability as the settings page)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def set_profile_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "set_profile",
        description="写入/更新一条用户画像键值(如 language=中文);用于沉淀用户长期偏好",
        audit=audit,
        write=True,
    )


__all__ = ["set_profile_tool"]
