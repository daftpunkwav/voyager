"""Memory capability group (the aggregated memory surface + turn rating).
Zero-logic aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.memory.memory import register as _memory
from agent.capabilities.memory.rate_turn import register as _rate_turn


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _memory(reg, deps)
    _rate_turn(reg, deps)
