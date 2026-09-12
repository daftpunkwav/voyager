"""Subagent system: dispatch, instance state machine, seven modes,
user-defined registry.
"""

from agent.subagent.instance import SubagentInstance, SubStatus, TaskBook
from agent.subagent.modes import Mode, ModeLimits, run_mode
from agent.subagent.registry import SubagentDef, SubagentRegistry
from agent.subagent.spawn import Spawner

__all__ = [
    "Mode",
    "ModeLimits",
    "Spawner",
    "SubStatus",
    "SubagentDef",
    "SubagentInstance",
    "SubagentRegistry",
    "TaskBook",
    "run_mode",
]
