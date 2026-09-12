"""recall_memory tool: retrieval-style memory query (profile / episodic /
semantic hits, source-tagged)."""

from __future__ import annotations

from agent.contracts import SkillRecallSource
from agent.tools.core.base import AgentTool


def recall_memory_tool(loader: SkillRecallSource) -> AgentTool:
    def recall_memory(query: str, limit: int = 8) -> list:
        return loader.recall(query, limit)

    return AgentTool(
        name="recall_memory",
        description="检索式记忆查询:画像/情节/语义三类命中,标注来源",
        handler=recall_memory,
        concurrent_safe=True,
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    )


__all__ = ["recall_memory_tool"]
