"""Memory capability group (recall / snapshot / clear / profile writes).
Zero-logic aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.memory.clear_memory import register as _clear_memory
from agent.capabilities.memory.delete_profile import register as _delete_profile
from agent.capabilities.memory.get_memory import register as _get_memory
from agent.capabilities.memory.rate_turn import register as _rate_turn
from agent.capabilities.memory.recall_memory import register as _recall_memory
from agent.capabilities.memory.set_profile import register as _set_profile


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _recall_memory(reg, deps)
    _rate_turn(reg, deps)
    _get_memory(reg, deps)
    _clear_memory(reg, deps)
    _set_profile(reg, deps)
    _delete_profile(reg, deps)
