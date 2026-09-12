"""register_subagent tool: persist a user-built subagent definition (same
capability as the team page form; audited as actor=agent)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def register_subagent_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "register_subagent",
        description=(
            "登记一个自定义 subagent 定义(名字/描述/模式/工具白名单/轮数与网络上限/只读);"
            "登记后可用 spawn_subagent(persona=名字) 派出"
        ),
        audit=audit,
        write=True,
    )


__all__ = ["register_subagent_tool"]
