"""Plan capability group (the plan review gate). Zero-logic aggregation:
import each capability file and register it. Durable goals live in the team
group (capabilities/team/goal.py)."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.plan.plan import register as _plan


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _plan(reg, deps)
