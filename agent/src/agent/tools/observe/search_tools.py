"""search_tools tool: find roster tools by keyword before activating them
(same engine as the capability)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def search_tools_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "search_tools",
        description=(
            "按关键词在当前工具名册中检索(名字与描述的词法匹配);"
            "不知道确切工具名时先查这里,再用 activate_tools 激活"
        ),
        audit=audit,
        concurrent_safe=True,
    )


__all__ = ["search_tools_tool"]
