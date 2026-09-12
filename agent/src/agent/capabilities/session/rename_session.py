"""rename_session capability: rename a chat session."""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(reg, name="rename_session", description="Rename a chat session")
    def rename_session(session_id: str, title: str) -> dict:
        deps.sessions.rename(session_id, title.strip()[:40])
        return {"session_id": session_id, "title": title.strip()[:40]}
