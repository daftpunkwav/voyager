"""delete_profile capability: delete one user-profile key-value (no error
when the key is absent).

`delete_profile()` is the one implementation; the capability and the agent's
delete_profile tool both bind it.
"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.memory import Memory


def delete_profile(memory: Memory, key: str) -> dict:
    cleaned = (key or "").strip()
    if not cleaned:
        raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "profile key must not be empty")
    memory.profile.delete(cleaned)
    return {"key": cleaned, "ok": True}


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="delete_profile",
        description="Delete one user-profile key-value (no error when the key is absent)",
    )
    def _delete_profile(key: str) -> dict:
        return delete_profile(deps.memory, key)
