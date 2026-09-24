"""Team capability group (subagents, run control, board, durable goals).
Zero-logic aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.team.agent_instance import register as _agent_instance
from agent.capabilities.team.board import register as _board
from agent.capabilities.team.goal import register as _goal
from agent.capabilities.team.subagent import register as _subagent
from agent.capabilities.team.taskboard import register as _taskboard


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _subagent(reg, deps)
    _agent_instance(reg, deps)
    _board(reg, deps)
    _goal(reg, deps)
    _taskboard(reg, deps)
