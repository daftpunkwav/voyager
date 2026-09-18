"""describe_tool tool: full metadata for one roster entry (same capability
as the settings tool catalog)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def describe_tool_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "describe_tool",
        description="查询单个工具的完整元数据(说明/分类/参数 schema);先用 list_tools 拿到名字",
        audit=audit,
        concurrent_safe=True,
    )


__all__ = ["describe_tool_tool"]
