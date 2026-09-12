"""request_context tool: a subagent asks the master for extra context.

Context is not shared directly: a subagent holds only its own task's context;
when broader context is needed (user profile, what other subagents are doing),
it requests it here and the master side returns only a summary.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.tools.core.base import AgentTool

ContextProvider = Callable[[str], dict[str, Any]]  # (request reason) -> summary dict


def request_context_tool(provider: ContextProvider) -> AgentTool:
    def request_context(need: str) -> dict:
        return provider(need)

    return AgentTool(
        name="request_context",
        description="向主 agent 申请额外上下文(用户画像/其他 subagent 状态等),说明用途",
        handler=request_context,
        concurrent_safe=True,
        schema={
            "type": "object",
            "properties": {"need": {"type": "string"}},
            "required": ["need"],
        },
    )


__all__ = ["request_context_tool"]
