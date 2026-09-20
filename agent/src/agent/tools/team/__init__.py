"""Team tool group: the subagent / agent_instance / board / goal surfaces in
four tools — each binds the same-name capability (audit symmetry, schema
derived from the capability). Zero-logic aggregation; registration happens
in build_agent after the registry exists."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks
from agent.tools.team.agent_instance import agent_instance_tool
from agent.tools.team.board import board_tool
from agent.tools.team.goal import goal_tool
from agent.tools.team.subagent import subagent_tool


def team_tools(registry: Registry, audit: AuditSinks | None = None) -> dict[str, AgentTool]:
    tools = (
        subagent_tool(registry, audit),
        agent_instance_tool(registry, audit),
        board_tool(registry, audit),
        goal_tool(registry, audit),
    )
    return {t.name: t for t in tools}


__all__ = ["team_tools"]
