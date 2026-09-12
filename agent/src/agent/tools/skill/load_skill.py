"""load_skill tool: on-demand full text of one skill (the index is already
resident in the system prompt)."""

from __future__ import annotations

from agent.contracts import SkillRecallSource
from agent.tools.core.base import AgentTool


def load_skill_tool(loader: SkillRecallSource) -> AgentTool:
    def load_skill(name: str) -> str:
        return loader.skill_text(name)

    return AgentTool(
        name="load_skill",
        description="按需读取某个 skill 的全文(索引已在上下文里,这里取全文)",
        handler=load_skill,
        concurrent_safe=True,
        schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    )


__all__ = ["load_skill_tool"]
