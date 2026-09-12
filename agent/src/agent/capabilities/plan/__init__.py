"""Plan capability group (plan review gate toggle, human side). Zero-logic
aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.plan.goal_manage import register as _goal_manage
from agent.capabilities.plan.plan_mode_set import register as _plan_mode_set


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _plan_mode_set(reg, deps)
    _goal_manage(reg, deps)
