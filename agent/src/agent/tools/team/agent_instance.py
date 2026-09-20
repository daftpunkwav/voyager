"""agent_instance tool: run control in one tool — cancel / pause / resume /
checkpoints / abandon, bound to the same agent_instance capability."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def agent_instance_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "agent_instance",
        description=(
            "运行实例控制(子代理与主对话实例),action:"
            " cancel(id_or_name,'chat'=主对话,紧急停止)/"
            " pause(id_or_name,协作式暂停,步骤边界生效)/"
            " resume(run_id,continue_run 从检查点恢复)/"
            " checkpoints(可恢复/可放弃检查点清单)/"
            " abandon(run_id,删除盘上检查点,不可逆)"
        ),
        audit=audit,
        write=True,
    )


__all__ = ["agent_instance_tool"]
