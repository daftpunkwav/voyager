"""Plan capability group (plan review gate + durable goals). Zero-logic
aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.plan.goal_manage import register as _goal_manage
from agent.capabilities.plan.plan import register as _plan


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _plan(reg, deps)
    _goal_manage(reg, deps)
