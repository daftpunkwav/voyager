"""Tests for the skill tool's propose action (validation ladder, on-disk
shape, SkillLoader indexing) and the retired-confirm policy gate."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from agent.llm import ToolCall
from agent.policy import PolicyEngine
from agent.skills.loader import SkillLoader
from agent.tools.core.base import Toolbelt
from agent.tools.skill.skill import skill_tool
from agent.tools.skill.skill_ops import propose_skill
from platform_contracts import ServiceError


@pytest.fixture()
def skills_dir(tmp_path: Path) -> Path:
    s_dir = tmp_path / "skills"
    s_dir.mkdir(parents=True, exist_ok=True)
    return s_dir


class TestProposeSkill:
    def test_propose_skill_success(self, skills_dir: Path) -> None:
        tool = skill_tool(
            loader=SkillLoader([skills_dir]), skills_dir=skills_dir
        )  # duck-typed loader
        res = asyncio.run(
            tool.handler(
                action="propose",
                name="python-list-quiz",
                description="Python 列表教学与测验流程",
                content="## 步骤\n1. 介绍列表基础\n2. 出题测验\n3. 错题讲解",
            )
        )
        assert res["name"] == "python-list-quiz" and res["updated"] is False

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
        with pytest.raises(ServiceError) as exc:
            propose_skill(skills_dir, "Invalid Name With Spaces", "描述", "内容")
        assert "invalid skill name" in str(exc.value)

    def test_empty_description_rejected(self, skills_dir: Path) -> None:
        with pytest.raises(ServiceError) as exc:
            propose_skill(skills_dir, "valid-skill", "  ", "内容")
        assert "description" in str(exc.value)

    def test_empty_content_rejected(self, skills_dir: Path) -> None:
        with pytest.raises(ServiceError) as exc:
            propose_skill(skills_dir, "valid-skill", "描述", "")
        assert "content" in str(exc.value)

    def test_update_existing_skill(self, skills_dir: Path) -> None:
        propose_skill(skills_dir, "keep-skill", "描述", "内容")
        out = propose_skill(skills_dir, "keep-skill", "新描述", "新内容")
        assert out["updated"] is True


class TestPolicyGate:
    """Skill-library writes land in the resident index next turn; the
    confirm channel is retired, so proposals land directly (the permission
    modes decide reachability; the skills subtree stays shell/file-proof via
    the fs guards)."""

    async def test_writes_without_confirmation_by_default(self, skills_dir: Path) -> None:
        tool = skill_tool(
            loader=SkillLoader([skills_dir]), skills_dir=skills_dir
        )  # duck-typed loader
        belt = Toolbelt({tool.name: tool}, PolicyEngine())
        out = await belt.call_detailed(
            ToolCall(
                "1",
                "skill",
                {"action": "propose", "name": "gated-skill", "description": "d", "content": "c"},
            )
        )
        assert out.ok is True
        assert "[需确认]" not in out.text
        assert (skills_dir / "gated-skill" / "SKILL.md").exists()


class TestSkillToolWrapper:
    """The skill tool's handler-side translation: ServiceError becomes
    model-readable failure text, load misses stay readable. The loader duck
    type is the production OnDemandLoader (skill_text + load recording)."""

    def _tool(self, skills_dir: Path):
        from agent.context.loader import OnDemandLoader

        loader = OnDemandLoader(skills=SkillLoader([skills_dir]))
        return skill_tool(loader=loader, skills_dir=skills_dir)

    def test_unknown_action_gets_readable_hint(self, skills_dir: Path) -> None:
        out = asyncio.run(self._tool(skills_dir).handler(action="delete", name="x"))
        assert out == "[参数错误] 未知 action: delete(可选 load/propose)"

    def test_load_missing_skill_gets_readable_error(self, skills_dir: Path) -> None:
        out = asyncio.run(self._tool(skills_dir).handler(action="load", name="no-such-skill"))
        assert out == "[参数错误] 没有 skill: no-such-skill(未批准或已删除)"

    def test_load_returns_full_text(self, skills_dir: Path) -> None:
        propose_skill(skills_dir, "loadable", "描述", "## 内容")
        out = asyncio.run(self._tool(skills_dir).handler(action="load", name="loadable"))
        assert "# loadable" in out and "## 内容" in out

    def test_propose_service_error_becomes_readable_text(self, skills_dir: Path) -> None:
        out = asyncio.run(
            self._tool(skills_dir).handler(
                action="propose", name="Bad Name", description="d", content="c"
            )
        )
        assert out.startswith("[参数错误] skill(action=propose):")
        assert "invalid skill name" in out
        assert "lowercase words joined by hyphens" in out  # the hint rides along

    def test_propose_error_without_hint_stays_readable(self, skills_dir: Path) -> None:
        out = asyncio.run(
            self._tool(skills_dir).handler(
                action="propose", name="ok-name", description="", content="c"
            )
        )
        assert out == "[参数错误] skill(action=propose): description must not be empty"
