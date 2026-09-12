"""install_plugin tool: copy a plugin into plugins/ without approving it
(L2 confirm; approval stays with the user)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def install_plugin_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "install_plugin",
        description=(
            "安装一个插件(zip_path 或 source_dir 二选一,须位于工作目录或附加根内);"
            "安装后仍未批准、不会加载——批准只能由用户在设置页完成;需用户确认"
        ),
        audit=audit,
        write=True,
        irreversible=True,
    )


__all__ = ["install_plugin_tool"]
