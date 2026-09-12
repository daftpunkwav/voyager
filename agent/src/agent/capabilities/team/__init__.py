"""Team capability group (subagent definitions, run governance, resumable
checkpoints). Zero-logic aggregation: import each capability file and
register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.team.abandon_resumable_checkpoint import (
    register as _abandon_resumable_checkpoint,
)
from agent.capabilities.team.cancel_run import register as _cancel_run
from agent.capabilities.team.list_resumable_checkpoints import (
    register as _list_resumable_checkpoints,
)
from agent.capabilities.team.list_subagents import register as _list_subagents
from agent.capabilities.team.pause_run import register as _pause_run
from agent.capabilities.team.register_subagent import register as _register_subagent
from agent.capabilities.team.resume_run import register as _resume_run


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _list_subagents(reg, deps)
    _pause_run(reg, deps)
    _cancel_run(reg, deps)
    _register_subagent(reg, deps)
    _list_resumable_checkpoints(reg, deps)
    _abandon_resumable_checkpoint(reg, deps)
    _resume_run(reg, deps)
