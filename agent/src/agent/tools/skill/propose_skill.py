"""propose_skill tool: propose saving a workflow or pedagogical SOP as a persistent skill.

Allows the agent to crystallize and persist learned domain SOPs, office workflows,
or pedagogical problem-solving steps into reusable skills. Persists to
`workspace/skills/<name>/SKILL.md`, automatically indexed by SkillLoader.

Responsibilities:
- Validate skill naming convention (lowercase kebab-case, no path traversal).
- Validate content boundaries to prevent context runaway.
- Atomically persist Markdown skill file with standard header structure.
- Report indexing readiness for subsequent on-demand loads.
"""

from __future__ import annotations

import re
from pathlib import Path

from agent.tools.core.base import AgentTool

_MAX_NAME_LENGTH = 64
_MAX_DESC_CHARS = 2_000
_MAX_CONTENT_CHARS = 100_000


def propose_skill_tool(skills_dir: str | Path) -> AgentTool:
    dir_path = Path(skills_dir)

    def propose_skill(name: str, description: str, content: str) -> str:
        clean_name = name.strip().lower()
        if len(clean_name) > _MAX_NAME_LENGTH:
            return f"[参数错误] propose_skill: 技能名称过长 (最多 {_MAX_NAME_LENGTH} 字符)。"
        if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", clean_name):
            return (
                f"[参数错误] propose_skill: 技能名称 '{name}' 不合法。"
                "请使用小写英文单词及连字符格式 (如 python-concept-quiz 或 meeting-summary)。"
            )
        clean_desc = description.strip()
        if not clean_desc:
            return "[参数错误] propose_skill: 技能描述 (description) 不能为空。"
        if len(clean_desc) > _MAX_DESC_CHARS:
            return f"[参数错误] propose_skill: 技能描述过长 (最多 {_MAX_DESC_CHARS} 字符)。"
        clean_content = content.strip()
        if not clean_content:
            return "[参数错误] propose_skill: 技能内容 (content) 不能为空。"
        if len(clean_content) > _MAX_CONTENT_CHARS:
            return f"[参数错误] propose_skill: 技能内容过长 (最多 {_MAX_CONTENT_CHARS} 字符)。"

        target_dir = dir_path / clean_name
        target_dir.mkdir(parents=True, exist_ok=True)
        skill_file = target_dir / "SKILL.md"
        is_update = skill_file.exists()

        text = f"# {clean_name}\n\n{clean_desc}\n\n{clean_content}\n"
        try:
            skill_file.write_text(text, encoding="utf-8")
        except OSError as exc:
            return f"[写入失败] 无法保存技能文件: {exc}"

        status_msg = "已更新" if is_update else "已保存"
        return (
            f"[技能{status_msg}] 技能 '{clean_name}' {status_msg}并加入索引。"
            f"未来可在类似任务中自动检索，或通过 load_skill(name='{clean_name}') 查阅。"
        )

    return AgentTool(
        name="propose_skill",
        description="提议并将有效的办公流程或教学解题方法沉淀为新技能(写入持久化技能库，立即可被索引读取)",
        handler=propose_skill,
        dimension="skill",
        write=True,
        schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "技能英文短标识，如 python-recursion-guide",
                },
                "description": {"type": "string", "description": "技能一句话用途概述"},
                "content": {"type": "string", "description": "技能的 Markdown 格式指引与操作步骤"},
            },
            "required": ["name", "description", "content"],
        },
    )


__all__ = ["propose_skill_tool"]
