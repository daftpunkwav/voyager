"""Skill capability group (index + on-demand full text). Zero-logic
aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.skill.list_skills import register as _list_skills
from agent.capabilities.skill.load_skill import register as _load_skill


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _list_skills(reg, deps)
    _load_skill(reg, deps)
