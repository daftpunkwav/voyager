"""list_tools tool: the full tool roster as the model could see it (same
capability as the team page's allowlist picker)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def list_tools_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "list_tools",
        description="列出当前完整工具名册(名字+说明),含各域桥接工具;登记 subagent 白名单前先查",
        audit=audit,
        concurrent_safe=True,
    )


__all__ = ["list_tools_tool"]
