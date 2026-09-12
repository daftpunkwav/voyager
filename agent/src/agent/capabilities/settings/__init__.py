"""Settings capability group (schema listing + value changes). Zero-logic
aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.settings.get_settings import register as _get_settings
from agent.capabilities.settings.set_setting import register as _set_setting


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _get_settings(reg, deps)
    _set_setting(reg, deps)
