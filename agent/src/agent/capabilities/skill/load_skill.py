"""load_skill capability: on-demand full text of one skill.

Same name and operation as the agent's load_skill tool (both bind to
SkillLoader.full_text); the capability adds the human-facing envelope and
translates the loader's KeyError to NOT_FOUND.
"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="load_skill",
        description="Read the full text of a skill on demand; same operation as the agent's load_skill tool",
    )
    def load_skill(name: str) -> dict:
        try:
            text = deps.skills.full_text(name)
        except KeyError:
            # The loader layer raises KeyError (locked by unit tests); the capability
            # layer translates it to NOT_FOUND so callers never see a raw internal
            # exception (unapproved and deleted skills both land here).
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND, f"no such skill: {name}") from None
        return {"name": name, "text": text}
