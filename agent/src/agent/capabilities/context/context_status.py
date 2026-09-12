"""context_status capability: context-window usage of a chat session.

Same name, same engine as the agent's context_status tool: both bind to
agent.context.operations.context_status. The capability form adds session
addressing (any session, default: the active one).
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps
from agent.context.operations import context_status as _status_op


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="context_status",
        description="Context window usage of a chat session (default: the active one); same operation as the agent's context_status tool",
    )
    def context_status(session_id: str = "") -> dict:
        inst = deps.sessions.instance_for(deps.sessions.target_id(session_id))
        if inst is None:
            return {"error": "session has no live context yet"}
        return _status_op(instance=inst)
