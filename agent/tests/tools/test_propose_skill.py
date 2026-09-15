"""Tests for the propose_skill tool."""

from __future__ import annotations

from pathlib import Path

import pytest
from agent.skills.loader import SkillLoader
from agent.tools.skill.propose_skill import propose_skill_tool


@pytest.fixture()
def skills_dir(tmp_path: Path) -> Path:
    s_dir = tmp_path / "skills"
    s_dir.mkdir(parents=True, exist_ok=True)
    return s_dir


class TestProposeSkill:
    def test_propose_skill_success(self, skills_dir: Path) -> None:
        tool = propose_skill_tool(skills_dir)
        res = tool.handler(
            name="python-list-quiz",
            description="Python 列表教学与测验流程",
            content="## 步骤\n1. 介绍列表基础\n2. 出题测验\n3. 错题讲解",
        )
        assert "[技能已保存]" in res
        assert "python-list-quiz" in res

        # Verify on-disk file
        skill_file = skills_dir / "python-list-quiz" / "SKILL.md"
        assert skill_file.exists()
        text = skill_file.read_text(encoding="utf-8")
        assert "# python-list-quiz" in text
        assert "Python 列表教学与测验流程" in text
        assert "## 步骤" in text

        # Verify SkillLoader can index and read it
        loader = SkillLoader([skills_dir])
        index = loader.index()
        assert any(item["name"] == "python-list-quiz" for item in index)
        full_text = loader.full_text("python-list-quiz")
        assert "Python 列表教学与测验流程" in full_text

    def test_invalid_skill_name(self, skills_dir: Path) -> None:
        tool = propose_skill_tool(skills_dir)
        res = tool.handler(
            name="Invalid Name With Spaces",
            description="描述",
            content="内容",
        )
        assert "[参数错误]" in res
        assert "不合法" in res

    def test_empty_description_rejected(self, skills_dir: Path) -> None:
        tool = propose_skill_tool(skills_dir)
        res = tool.handler(
            name="valid-skill",
            description="  ",
            content="内容",
        )
        assert "[参数错误]" in res
        assert "描述" in res

    def test_empty_content_rejected(self, skills_dir: Path) -> None:
        tool = propose_skill_tool(skills_dir)
        res = tool.handler(
            name="valid-skill",
            description="描述",
            content="",
        )
        assert "[参数错误]" in res
        assert "内容" in res
