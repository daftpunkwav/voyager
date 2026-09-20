"""tools tool: the tool roster's self-management surface in one tool —
list / describe / search, bound to the same tools capability (audit
symmetry; schema derived from the capability)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def tools_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "tools",
        description=(
            "工具面自管理:action list(全名册含域桥)/ describe(name,完整元数据含参数 schema)/"
            " search(query,limit,词法检索,名字不确定时先查再激活)"
        ),
        audit=audit,
        concurrent_safe=True,
    )


__all__ = ["tools_tool"]
