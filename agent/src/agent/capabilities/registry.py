"""Agent capability registry assembly: import each concern group and
register it into one Registry("agent"). Zero logic — order only.
"""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities import (
    context,
    extension,
    interact,
    jobs,
    memory,
    observe,
    plan,
    policy,
    session,
    settings,
    skill,
    team,
    tools,
    workspace,
)
from agent.capabilities.deps import CapabilityDeps


def build_agent_registry(deps: CapabilityDeps) -> Registry:
    reg = Registry("agent")
    settings.register(reg, deps)
    observe.register(reg, deps)
    skill.register(reg, deps)
    tools.register(reg, deps)
    team.register(reg, deps)
    extension.register(reg, deps)
    memory.register(reg, deps)
    interact.register(reg, deps)
    workspace.register(reg, deps)
    session.register(reg, deps)
    jobs.register(reg, deps)
    policy.register(reg, deps)
    plan.register(reg, deps)
    context.register(reg, deps)
    return reg


__all__ = ["build_agent_registry"]
