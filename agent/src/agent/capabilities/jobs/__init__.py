"""Jobs capability group (background tasks: list/reorder/cancel).
Zero-logic aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.jobs.jobs import register as _jobs


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _jobs(reg, deps)
