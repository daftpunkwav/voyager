"""Workspace capability group (plan/todo view). Zero-logic aggregation:
import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.workspace.todowrite import register as _todowrite


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _todowrite(reg, deps)
