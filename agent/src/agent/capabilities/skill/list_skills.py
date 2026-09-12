"""list_skills capability: the resident skill index (name + description).

Deliberately has no agent tool: the index is already resident in the system
prompt, so a tool would be redundant (see the parity exception list).
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(reg, name="list_skills", description="Skill index (resident: name + description)")
    def list_skills() -> list[dict]:
        return deps.skills.index()
