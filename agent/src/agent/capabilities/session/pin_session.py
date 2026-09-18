"""pin_session capability: toggle the pinned flag on a chat session."""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="pin_session",
        description="Pin or unpin a chat session in the sidebar list (human path)",
    )
    def pin_session(session_id: str, pinned: bool = True) -> dict:
        return deps.sessions.set_flags(session_id, pinned=pinned)
