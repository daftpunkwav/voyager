"""Tools capability group (the aggregated tools surface). Zero-logic
aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.tools.tools import register as _tools


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _tools(reg, deps)
