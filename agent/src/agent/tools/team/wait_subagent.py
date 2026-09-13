"""wait_subagent tool: block until a dispatched subagent finishes and carry
the full result back into the conversation (same engine as the capability)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def wait_subagent_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "wait_subagent",
        description=(
            "等待已派出的 subagent(按 id 或名字)结束并取回完整结果;"
            "下一步动作依赖其产出时使用,知会型任务不必等(完成会主动通报)"
        ),
        audit=audit,
    )


__all__ = ["wait_subagent_tool"]
