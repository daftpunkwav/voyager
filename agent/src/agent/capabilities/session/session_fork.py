"""session_fork capability: fork a session into a new one carrying a history
copy."""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="session_fork",
        description="Fork a session (default: the active one) into a new session carrying a history copy; same operation as the agent's session_fork tool",
    )
    def session_fork(source_session_id: str = "", title: str = "") -> dict:
        return deps.sessions.fork(source_session_id, title=title.strip()[:40])
