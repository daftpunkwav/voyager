"""context capability: the human REST surface for context-window management —
one action parameter covers status/compact.

Same name and same engine operations as the agent's context tool — both bind
agent.context.operations (one implementation, two drivers). The capability
form adds session addressing (any session, default: the active one) and
persists the session after a compaction.
"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.context.operations import compact_context as _compact_op
from agent.context.operations import context_status as _status_op


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="context",
        description=(
            "Context-window management: action status (usage: window/used/percent/"
            "threshold) or compact (LLM-driven transcript restructure with a"
            " mechanical fallback); session_id addresses a session, default active"
        ),
    )
    async def context(action: str = "status", session_id: str = "") -> dict:
        inst = deps.sessions.instance_for(deps.sessions.target_id(session_id))
        if inst is None:
            return {"error": "session has no live context yet"}
        if action == "status":
            return _status_op(instance=inst)
        if action == "compact":
            report = await _compact_op(instance=inst)
            if report is None:
                return {"mode": "skipped", "detail": "already within the compact target"}
            deps.sessions.persist(inst.session)
            return report
        raise ServiceError(
            "agent",
            ErrorSuffix.INVALID_INPUT,
            f"unknown action: {action!r}",
            hint="valid actions: status/compact",
        )
