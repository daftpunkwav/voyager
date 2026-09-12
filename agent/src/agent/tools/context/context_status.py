"""context_status tool: the model reads its own context-window usage.

Resolves the executing instance through the current_instance ContextVar and
forwards to the SAME operation the human capability uses
(agent.context.operations.context_status) — one implementation, two drivers.
"""

from __future__ import annotations

from agent.context.operations import context_status as _status_op
from agent.runtime.current import current_instance
from agent.tools.core.base import AgentTool

_NO_INSTANCE = {"error": "当前没有运行中的实例上下文"}


def context_status_tool() -> AgentTool:
    async def context_status() -> dict:
        """Usage facts for the live transcript (window, used, threshold)."""
        inst = current_instance.get()
        if inst is None:
            return dict(_NO_INSTANCE)
        return _status_op(instance=inst)

    return AgentTool(
        name="context_status",
        description=(
            "查看当前上下文窗口用量(窗口大小/已用 tokens/百分比/压缩阈值);"
            "规划大批量工作前先看一眼,决定是否需要先压缩"
        ),
        handler=context_status,
        dimension="none",
        concurrent_safe=True,
    )


__all__ = ["context_status_tool"]
