"""get_resource_quota tool: today's token usage and the daily quota (same
capability as the usage page)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def get_resource_quota_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "get_resource_quota",
        description="查看今日已用 token 与每日配额上限(0 = 不限);规划大批量工作前先看余量",
        audit=audit,
        concurrent_safe=True,
    )


__all__ = ["get_resource_quota_tool"]
