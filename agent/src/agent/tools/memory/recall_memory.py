"""recall_memory tool: retrieval-style memory query (profile / episodic /
semantic hits, source-tagged).

One-shot requests are bounded: the limit is clamped to [_MIN_LIMIT,
_MAX_LIMIT] so a single call cannot pull an unbounded result set; large
outputs still flow through the shared tool-result budget (spill to file).
"""

from __future__ import annotations

from agent.contracts import SkillRecallSource
from agent.tools.core.base import AgentTool

#: Default and upper bound for one-shot recall requests (top-of-file so the
#: budget is trivial to retune).
_DEFAULT_LIMIT = 8
_MAX_LIMIT = 20
_MIN_LIMIT = 1


def recall_memory_tool(loader: SkillRecallSource) -> AgentTool:
    def recall_memory(query: str, limit: int = _DEFAULT_LIMIT) -> list:
        # Schema validation normally guarantees an int, but explicit null /
        # wrong-type values must degrade to the default, never raise.
        count = limit if isinstance(limit, int) and not isinstance(limit, bool) else _DEFAULT_LIMIT
        return loader.recall(query, max(_MIN_LIMIT, min(count, _MAX_LIMIT)))

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
