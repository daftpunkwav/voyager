"""session_create capability: create a fresh chat session (does not switch
the active one)."""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="session_create",
        description="Create a fresh chat session (does not switch the active one); same operation as the agent's session_create tool",
    )
    def session_create(title: str = "", persona: str = "orchestrator") -> dict:
        return deps.sessions.create(title=title.strip()[:40], persona=persona)
