"""memory tool: the agent's whole memory surface in one tool —
query/recall/remember/forget/clear, bound to the same memory capability the
settings page drives (audit symmetry; schema derived from the capability).
"""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def memory_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "memory",
        description=(
            "记忆域:action query(快照:画像/情节/语义/工作/保留期)/"
            " recall(query,limit,检索式查询,标注来源)/ remember(key,value,写入画像)/"
            " forget(key,删除画像键,不存在不报错)/ clear(zone,清空区,不可逆)"
        ),
        audit=audit,
        write=True,
    )


__all__ = ["memory_tool"]
