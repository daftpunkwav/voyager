"""compact_context capability: compact a chat session's context via the LLM
editor.

Same name, same engine as the agent's compact_context tool: both bind to
agent.context.operations.compact_context. The capability form adds session
addressing and persists the session after a compaction.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps
from agent.context.operations import compact_context as _compact_op


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="compact_context",
        description="Compact a chat session's context via the LLM editor (default: the active one); same operation as the agent's compact_context tool",
    )
    async def compact_context(session_id: str = "") -> dict:
        inst = deps.sessions.instance_for(deps.sessions.target_id(session_id))
        if inst is None:
            return {"error": "session has no live context yet"}
        report = await _compact_op(instance=inst)
        if report is None:
            return {"mode": "skipped", "detail": "already within the compact target"}
        deps.sessions.persist(inst.session)
        return report
