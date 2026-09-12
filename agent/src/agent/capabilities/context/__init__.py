"""Context capability group (human-side context management). Zero-logic
aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.context.compact_context import register as _compact_context
from agent.capabilities.context.context_status import register as _context_status
from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _context_status(reg, deps)
    _compact_context(reg, deps)
