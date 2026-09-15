"""Plan-mode tools (plan review gate). Zero-logic aggregation: import each
tool file and expose its factory."""

from __future__ import annotations

from agent.context.plan_gate import PlanGates
from agent.tools.core.base import AgentTool
from agent.tools.interact.question_broker import AskUser
from agent.tools.plan.exit_plan_mode import exit_plan_mode_tool
from agent.tools.plan.goal_read import goal_read_tool
from agent.tools.plan.goal_write import goal_write_tool
from agent.tools.plan.scratchpad import scratchpad_tool


def plan_tools(gates: PlanGates, asker: AskUser) -> dict[str, AgentTool]:
    exit_plan_mode = exit_plan_mode_tool(gates, asker)
    return {exit_plan_mode.name: exit_plan_mode}


def goal_tools(goals) -> dict[str, AgentTool]:
    goal_read = goal_read_tool(goals)
    goal_write = goal_write_tool(goals)
    return {goal_read.name: goal_read, goal_write.name: goal_write}


__all__ = ["goal_tools", "plan_tools", "scratchpad_tool"]
