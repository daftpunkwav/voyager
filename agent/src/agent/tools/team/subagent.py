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
            " send(id_or_name,message,跟进等待输入的对话型实例;"
            "react 任务不续代,请带 board 结论重新 spawn)"
        ),
        audit=audit,
        write=True,
    )


__all__ = ["subagent_tool"]
