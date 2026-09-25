"""Subagent system: dispatch, instance state machine, seven modes,
user-defined registry.
"""

from agent.engine.instance import SubagentInstance, SubStatus, TaskBook
from agent.engine.modes import Mode, ModeLimits, run_mode
from agent.engine.registry import SubagentDef, SubagentRegistry
from agent.engine.spawn import Spawner

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
