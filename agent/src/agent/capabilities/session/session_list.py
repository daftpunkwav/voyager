"""session_list capability: list chat sessions (the human path).

The same SessionManager also backs the agent's session_list tool, so the
human and agent paths drive one engine.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="session_list",
        description="List chat sessions (most recent first, active flagged); same operation as the agent's session_list tool",
    )
    def session_list() -> dict:
        return {"sessions": deps.sessions.list(), "active": deps.sessions.active_id()}
