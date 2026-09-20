"""Skill tool group: the aggregated skill surface (load / propose).
Zero-logic aggregation."""

from __future__ import annotations

from pathlib import Path

from agent.contracts import SkillRecallSource
from agent.tools.core.base import AgentTool
from agent.tools.skill.skill import skill_tool

__all__ = ["skill_tools"]


def skill_tools(loader: SkillRecallSource, skills_dir: str | Path) -> dict[str, AgentTool]:
    tool = skill_tool(loader, skills_dir)
    return {tool.name: tool}
