"""cancel_run tool: emergency-stop a running subagent (same capability the
team page button calls; audited as actor=agent)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def cancel_run_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "cancel_run",
        description="紧急停止一个运行中的 subagent(按 id 或名字;'chat' = 主对话实例)",
        audit=audit,
        write=True,
    )


__all__ = ["cancel_run_tool"]
