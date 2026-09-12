"""reload_user_hooks tool: reload the declarative hooks under
workspace/hooks/ (L2 confirm: a reload activates whatever is on disk)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def reload_user_hooks_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "reload_user_hooks",
        description="重新加载 workspace/hooks/ 下的声明式钩子(无需重启;会激活目录里的全部钩子,需用户确认)",
        audit=audit,
        write=True,
        irreversible=True,
    )


__all__ = ["reload_user_hooks_tool"]
