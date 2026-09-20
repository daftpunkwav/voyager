"""skill tool: the agent's skill domain in one tool — action load (fetch one
skill's full text; the index is already resident in the system prompt) /
propose (persist a workflow SOP into the skill library, indexed immediately).

Same name and same operations as the human skill capability — both bind
skill_ops (one implementation, two drivers). Handler-side translation only:
ServiceError becomes model-readable failure text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from platform_contracts import ServiceError

from agent.tools.core.base import AgentTool
from agent.tools.skill.skill_ops import propose_skill as _propose_skill

LoaderLike = Any  # SkillLoader (only skill_text is used; duck-typed)


def skill_tool(loader: LoaderLike, skills_dir: str | Path) -> AgentTool:
    async def skill(
        action: str, name: str = "", description: str = "", content: str = ""
    ) -> dict | str:
        if action == "load":
            try:
                return loader.skill_text(name)
            except KeyError:
                return f"[参数错误] 没有 skill: {name}(未批准或已删除)"
        if action == "propose":
            try:
                return _propose_skill(skills_dir, name, description, content)
            except ServiceError as exc:
                hint = f";{exc.body.hint}" if exc.body.hint else ""
                return f"[参数错误] skill(action=propose): {exc.body.message}{hint}"
        return f"[参数错误] 未知 action: {action}(可选 load/propose)"

    return AgentTool(
        name="skill",
        description=(
            "技能域,action: load(name,按需取全文;索引已在上下文里)/"
            " propose(name 小写英文-连字符, description, content 为 Markdown,"
            "把可复用的流程沉淀为技能,立即可被索引读取)"
        ),
        handler=skill,
        schema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["load", "propose"],
                    "description": "load 取全文 / propose 沉淀新技能",
                },
                "name": {
                    "type": "string",
                    "description": "技能英文短标识,如 python-recursion-guide",
                },
                "description": {"type": "string", "description": "propose:技能一句话用途概述"},
                "content": {"type": "string", "description": "propose:Markdown 格式的指引与步骤"},
            },
            "required": ["action"],
        },
        write=True,
        dimension="none",
    )


__all__ = ["skill_tool"]
