"""set_active_session capability: switch the active chat session.

Human-only by design: an agent moving the conversation the user is looking at
would break the conversational contract (interaction integrity, not privacy).
The agent side navigates instead; see the parity exception list.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="set_active_session",
        description="Switch the active chat session (where session-less messages land)",
    )
    def set_active_session(session_id: str) -> dict:
        return deps.sessions.set_active(session_id)
