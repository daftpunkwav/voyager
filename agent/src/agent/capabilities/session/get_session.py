"""get_session capability: one session's persisted snapshot detail (history
included)."""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="get_session",
        description="One session's persisted snapshot detail (history included)",
    )
    def get_session(session_id: str) -> dict:
        snap = deps.sessions.snapshot(session_id)
        if snap is None:
            return {"session_id": session_id, "found": False}
        return {"found": True, **snap.to_dict()}
