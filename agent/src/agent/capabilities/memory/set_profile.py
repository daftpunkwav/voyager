"""set_profile capability: write/update one user-profile key-value.

`set_profile()` is the one implementation; the capability and the agent's
set_profile tool both bind it (empty key is INVALID_INPUT).
"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.memory import Memory


def set_profile(memory: Memory, key: str, value: str) -> dict:
    cleaned = (key or "").strip()
    if not cleaned:
        raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "profile key must not be empty")
    memory.profile.set(cleaned, value)
    return {"key": cleaned, "ok": True}


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(reg, name="set_profile", description="Write/update one user-profile key-value")
    def _set_profile(key: str, value: str) -> dict:
        return set_profile(deps.memory, key, value)
