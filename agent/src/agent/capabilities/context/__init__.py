"""Context capability group (human-side context management). Zero-logic
aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.context.context import register as _context
from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _context(reg, deps)
