"""compact_context tool: the model compacts its own transcript proactively.

Resolves the executing instance through the current_instance ContextVar and
forwards to the SAME operation the human capability uses
(agent.context.operations.compact_context). The compaction engine and the
trigger policy live in agent.context.editor / agent.context.governor.
"""

from __future__ import annotations

from agent.context.operations import compact_context as _compact_op
from agent.runtime.current import current_instance
from agent.tools.core.base import AgentTool

_NO_INSTANCE = {"error": "当前没有运行中的实例上下文"}


def compact_context_tool() -> AgentTool:
    async def compact_context() -> dict:
        """Restructure the live transcript now: the LLM editor decides what to
        keep, summarize, and drop; falls back to deterministic compression."""
        inst = current_instance.get()
        if inst is None:
            return dict(_NO_INSTANCE)
        report = await _compact_op(instance=inst)
        if report is None:
            return {"mode": "skipped", "detail": "已低于压缩目标,无需压缩"}
        verb = "已按计划重组上下文" if report.get("mode") == "plan" else "计划不可用,已机械压缩兜底"
        return {"detail": verb, **report}

    return AgentTool(
        name="compact_context",
        description=(
            "主动压缩当前对话上下文:由模型决定保留/摘要/丢弃哪些分段,"
            "腾出窗口空间;大批量工作(整理/索引/批量抓取)开始前建议先压缩"
        ),
        handler=compact_context,
        dimension="none",
    )


__all__ = ["compact_context_tool"]
