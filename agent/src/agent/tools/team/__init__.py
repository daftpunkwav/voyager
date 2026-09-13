"""Team tool group: subagent dispatch and run governance. Zero-logic
aggregation.

spawn_subagent binds master.dispatch_task; the governance tools bind the
agent capability registry (same capabilities the team page calls) — both
are registered in build_agent after the master exists.
"""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks
from agent.tools.team.abandon_resumable_checkpoint import abandon_resumable_checkpoint_tool
from agent.tools.team.cancel_run import cancel_run_tool
from agent.tools.team.list_resumable_checkpoints import list_resumable_checkpoints_tool
from agent.tools.team.list_subagents import list_subagents_tool
from agent.tools.team.pause_run import pause_run_tool
from agent.tools.team.read_board import read_board_tool
from agent.tools.team.register_subagent import register_subagent_tool
from agent.tools.team.resume_run import resume_run_tool
from agent.tools.team.spawn_subagent import DispatchFn, spawn_subagent_tool
from agent.tools.team.wait_subagent import wait_subagent_tool
from agent.tools.team.write_board import write_board_tool


def spawn_tool(dispatch: DispatchFn) -> dict[str, AgentTool]:
    tool = spawn_subagent_tool(dispatch)
    return {tool.name: tool}


def team_tools(
    registry: Registry,
    audit: AuditSinks | None = None,
    *,
    blackboard=None,
) -> dict[str, AgentTool]:
    tools = (
        list_subagents_tool(registry, audit),
        pause_run_tool(registry, audit),
        cancel_run_tool(registry, audit),
        resume_run_tool(registry, audit),
        register_subagent_tool(registry, audit),
        list_resumable_checkpoints_tool(registry, audit),
        abandon_resumable_checkpoint_tool(registry, audit),
        wait_subagent_tool(registry, audit),
        *(
            (read_board_tool(blackboard), write_board_tool(blackboard))
            if blackboard is not None
            else ()
        ),
    )
    return {t.name: t for t in tools}


__all__ = ["spawn_subagent_tool", "spawn_tool", "team_tools"]
