"""spawn_subagent tool: how a chat instance dispatches task subagents."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent.tools.core.base import AgentTool

DispatchFn = Callable[..., Awaitable[Any]]  # master.dispatch_task


def spawn_subagent_tool(dispatch: DispatchFn) -> AgentTool:
    async def spawn_subagent(
        goal: str,
        persona: str = "",
        mode: str = "",
        name: str = "",
        readonly: bool = False,
        allowed_tools: list[str] | None = None,
    ) -> dict:
        inst = await dispatch(
            goal,
            persona=persona,
            mode=mode or None,
            name=name,
            readonly=bool(readonly),
            # The explicit allowlist overrides the definition/preset whitelist;
            # dispatch validates it against this instance's surface and
            # freezes the intersection (narrow only, never wider).
            allowed_tools=tuple(allowed_tools) if allowed_tools else None,
        )
        status = getattr(inst.status, "value", inst.status)  # DeferredDispatch has a str
        return {"subagent_id": inst.id, "name": inst.name, "status": status}

    return AgentTool(
        name="spawn_subagent",
        description="派出 subagent 后台执行任务;完成后会主动通报结果。"
        "只读审查类任务传 readonly=true: 写工具真实缺席,不要只在目标里写「不准修改」。"
        "allowed_tools 可覆盖定义白名单,但只能收窄:超出本实例已有工具面的请求会被拒绝",
        handler=spawn_subagent,
        schema={
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "persona": {"type": "string"},
                "mode": {"type": "string"},
                "name": {"type": "string"},
                "readonly": {"type": "boolean"},
                "allowed_tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "覆盖定义白名单的工具列表(仅限本实例已拥有的工具,支持 notes__* 前缀)",
                },
            },
            "required": ["goal"],
        },
        # Side effect (creates a running instance): never retry on failure to
        # avoid duplicate instances (write-class tools are not retried)
        write=True,
    )


__all__ = ["spawn_subagent_tool"]
