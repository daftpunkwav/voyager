"""session_trace tool: fork lineage for a session — the ancestor chain it
was forked from and the direct children forked from it."""

from __future__ import annotations

from typing import Any

from agent.tools.core.base import AgentTool

_LineageSource = Any  # SessionManager (lineage(); duck-typed to avoid a master import)


def session_trace_tool(manager: _LineageSource) -> AgentTool:
    async def session_trace(session_id: str = "") -> dict:
        return manager.lineage(session_id)

    return AgentTool(
        name="session_trace",
        description=(
            "查看会话的分支血缘:上游祖先链与直接子会话;"
            "用于确认当前对话从哪次对话分叉、以及有哪些平行分支"
        ),
        handler=session_trace,
        dimension="none",
        concurrent_safe=True,
        schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "目标会话 id(空 = 当前会话)"}
            },
        },
    )


__all__ = ["session_trace_tool"]
