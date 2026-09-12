"""list_user_hooks tool: read-only listing of the hook json files under
workspace/hooks/ (same capability as the settings page)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def list_user_hooks_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "list_user_hooks",
        description="列出 workspace/hooks/ 下的钩子文件(文件名/触发事件/是否启用/是否已加载)",
        audit=audit,
        concurrent_safe=True,
    )


__all__ = ["list_user_hooks_tool"]
