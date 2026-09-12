"""set_setting capability: change one setting (secret and user_only items
are rejected by the settings framework for non-user actors)."""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ActorRef

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="set_setting",
        description="Change one setting (secret items are rejected by the framework)",
    )
    async def set_setting(key: str, value, _actor: ActorRef | None = None) -> dict:
        await deps.settings.set(key, value, _actor)
        return {"key": key, "ok": True}
