"""observe tool: operational self-observation in one tool — events / quota,
bound to the same observe capability (audit symmetry; schema derived from
the capability)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def observe_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "observe",
        description=(
            "自观测:action events(types 白名单限定,after_seq 增量,limit;"
            "任务完成/失败、服务健康、设置变更等,与活动页同源)/"
            " quota(今日 token 用量、成本与每日配额)"
        ),
        audit=audit,
        concurrent_safe=True,
    )


__all__ = ["observe_tool"]
