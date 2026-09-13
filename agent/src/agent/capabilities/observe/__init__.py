"""Observe capability group (quota, tool roster, persona catalog).
Zero-logic aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.observe.get_resource_quota import register as _get_resource_quota
from agent.capabilities.observe.list_personas import register as _list_personas
from agent.capabilities.observe.list_tools import register as _list_tools
from agent.capabilities.observe.search_tools import register as _search_tools


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _get_resource_quota(reg, deps)
    _list_personas(reg, deps)
    _list_tools(reg, deps)
    _search_tools(reg, deps)
