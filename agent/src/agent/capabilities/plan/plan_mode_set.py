"""plan_mode_set capability: toggle the session's plan review gate.

Human-only by design: the review gate decides when the agent may act, so the
switch must stay in human hands (parity exception list). In-memory state: a
restart ends any open review phase.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="plan_mode_set",
        description="Toggle the session's plan review gate (explore/design only until approved)",
    )
    def plan_mode_set(session_id: str, enabled: bool) -> dict:
        assert deps.plan_gates is not None, "plan gates not wired at assembly"
        deps.plan_gates.set(session_id, enabled)
        return {"session_id": session_id, "plan_mode": enabled}
