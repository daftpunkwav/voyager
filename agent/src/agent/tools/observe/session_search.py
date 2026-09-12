"""session_search tool: full-text search over past conversations (FTS
projection over the event log). Query text is data — phrase-quoted, never
search grammar."""

from __future__ import annotations

from agent.runtime.session_index import SessionIndex
from agent.tools.core.base import AgentTool


def session_search_tool(index: SessionIndex) -> AgentTool:
    async def session_search(query: str, limit: int = 8) -> list[dict] | str:
        needle = str(query or "").strip()
        if not needle:
            return "[参数错误] query 不能为空"
        index.catch_up()  # lazy fold: the index stays current without a live subscription
        hits = index.search(needle, limit=max(1, min(int(limit), 50)))
        if not hits:
            return f"未找到与「{needle[:80]}」相关的历史会话内容"
        return hits

    return AgentTool(
        name="session_search",
        description=(
            "全文检索历史会话内容(用户消息与助手回复);"
            "用于回忆之前做过的任务、结论与上下文;返回会话、时间与命中片段"
        ),
        handler=session_search,
        dimension="none",
        concurrent_safe=True,
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索关键词或短语"},
                "limit": {"type": "integer", "description": "返回条数上限(默认 8)"},
            },
            "required": ["query"],
        },
    )


__all__ = ["session_search_tool"]
