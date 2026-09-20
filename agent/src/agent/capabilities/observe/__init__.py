"""Observe capability group (events/quota, the persona catalog).
Zero-logic aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.observe.list_personas import register as _list_personas
from agent.capabilities.observe.observe import register as _observe


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _observe(reg, deps)
    _list_personas(reg, deps)
