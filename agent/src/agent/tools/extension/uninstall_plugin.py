"""uninstall_plugin tool: delete an unapproved plugin's directory
(irreversible, L2 confirm)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def uninstall_plugin_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "uninstall_plugin",
        description="删除一个未批准插件的目录(已批准的须先由用户撤销;不可逆,需用户确认)",
        audit=audit,
        write=True,
        irreversible=True,
    )


__all__ = ["uninstall_plugin_tool"]
