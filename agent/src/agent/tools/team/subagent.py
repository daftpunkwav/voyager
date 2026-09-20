"""subagent tool: spawn / list / register / unregister / wait / send in one
tool, bound to the same subagent capability (audit symmetry)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def subagent_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "subagent",
        description=(
            "subagent 域,action:"
            " spawn(goal 派出后台任务,persona/mode/name/readonly/allowed_tools 可选,"
            "白名单只能收窄本实例已有工具面)/"
            " list(定义与运行中实例)/"
            " register(name,description 等登记自定义定义)/ unregister(name 删除定义)/"
            " wait(id_or_name,timeout_s,阻塞等结果)/"
            " send(id_or_name,message,保留的续跑通道:用户聊天实例不可驱动,"
            "任务实例不原地续代——跟进请重新 spawn 并在 goal 里引用 board/前次结论)"
        ),
        audit=audit,
        write=True,
    )


__all__ = ["subagent_tool"]
