"""archive_session capability: toggle the archived flag on a chat session."""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="archive_session",
        description="Archive or unarchive a chat session (human path); archived sessions leave the default list",
    )
    def archive_session(session_id: str, archived: bool = True) -> dict:
        return deps.sessions.set_flags(session_id, archived=archived)
