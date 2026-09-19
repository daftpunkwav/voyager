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
    def session_fork(source_session_id: str = "", title: str = "", keep_messages: int = 0) -> dict:
        """keep_messages > 0 truncates the copied history to its first N
        entries (message-level fork from a chosen point in time)."""
        return deps.sessions.fork(
            source_session_id, title=title.strip()[:40], keep_messages=max(0, keep_messages)
        )
