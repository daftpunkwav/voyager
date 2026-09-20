"""Skill capability group (aggregated skill surface + the resident index).
Zero-logic aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.skill.list_skills import register as _list_skills
from agent.capabilities.skill.skill import register as _skill


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _skill(reg, deps)
    _list_skills(reg, deps)
