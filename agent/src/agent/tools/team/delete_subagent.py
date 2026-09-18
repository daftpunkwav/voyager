"""delete_subagent tool: remove a user-built subagent definition (same
capability as the settings page; audited as actor=agent)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def delete_subagent_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "delete_subagent",
        description="删除一个自定义 subagent 定义;已派出的实例不受影响,只是之后不能再以该名字派出",
        audit=audit,
        write=True,
    )


__all__ = ["delete_subagent_tool"]
