"""delete_session capability: delete a chat session (refused while its turn
is running)."""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="delete_session",
        description="Delete a chat session (refused while its turn is running)",
    )
    def delete_session(session_id: str) -> dict:
        return deps.sessions.delete(session_id)
