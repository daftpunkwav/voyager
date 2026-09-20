"""context tool: the model reads and compacts its own context window in one
tool — action status / compact.

Resolves the executing instance through the current_instance ContextVar and
forwards to the SAME operations the human context capability uses
(agent.context.operations) — one implementation, two drivers. The compaction
engine and the trigger policy live in agent.context.editor /
agent.context.governor.
"""

from __future__ import annotations

from agent.context.operations import compact_context as _compact_op
from agent.context.operations import context_status as _status_op
from agent.runtime.current import current_instance
from agent.tools.core.base import AgentTool

_NO_INSTANCE = {"error": "当前没有运行中的实例上下文"}


def context_tool() -> AgentTool:
    async def context(action: str = "status") -> dict:
        if action == "status":
            inst = current_instance.get()
            if inst is None:
                return dict(_NO_INSTANCE)
            return _status_op(instance=inst)
        if action == "compact":
            inst = current_instance.get()
            if inst is None:
                return dict(_NO_INSTANCE)
            report = await _compact_op(instance=inst)
            if report is None:
                return {"mode": "skipped", "detail": "已低于压缩目标,无需压缩"}
            verb = (
                "已按计划重组上下文"
                if report.get("mode") == "plan"
                else "计划不可用,已机械压缩兜底"
            )
            return {"detail": verb, **report}
        return {"error": f"[参数错误] 未知 action: {action}(可选 status/compact)"}

    return AgentTool(
        name="context",
        description=(
            "查看并管理当前上下文窗口,action:"
            " status(窗口大小/已用 tokens/百分比/压缩阈值;大批量工作前先看一眼)/"
            " compact(主动压缩:模型决定保留/摘要/丢弃,腾出窗口空间;建议大批量工作前先压缩)"
        ),
        handler=context,
        schema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "compact"],
                    "description": "status 查询用量 / compact 压缩当前上下文",
                },
            },
        },
        dimension="none",
    )


__all__ = ["context_tool"]
