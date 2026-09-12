"""list_subagents tool: registered definitions plus alive instances (same
capability as the team page list)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def list_subagents_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "list_subagents",
        description="列出已登记的 subagent 定义与当前存活的实例(id/名字/状态/目标/最近一步)",
        audit=audit,
        concurrent_safe=True,
    )


__all__ = ["list_subagents_tool"]
