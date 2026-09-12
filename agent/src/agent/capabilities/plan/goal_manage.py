"""goal_manage capability: create / pause / resume / clear a session's
durable goal. Human-only (parity list): the auto-continuation budget is
controlled from this surface, so the agent must not write it; the agent
reports progress through goal_write instead."""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.master.goal import ACTIVE, DONE, PAUSED

_VALID = {"create", "pause", "resume", "clear", "done"}


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="goal_manage",
        description="Create/pause/resume/clear the session's durable goal (drives auto-continuation)",
    )
    def goal_manage(session_id: str, action: str, text: str = "") -> dict:
        assert deps.goal_manager is not None, "goal manager not wired at assembly"
        goals = deps.goal_manager
        if action == "create":
            body = text.strip()
            if not body:
                raise ServiceError(
                    "agent", ErrorSuffix.INVALID_INPUT, "goal text must not be empty"
                )
            goal = goals.create(session_id, body[:500])
            return {"session": session_id, "status": goal.status, "text": goal.text}
        if action == "clear":
            goals.clear(session_id)
            return {"session": session_id, "cleared": True}
        if action not in {"pause", "resume", "done"}:
            raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, f"unknown action: {action!r}")
        status = {PAUSED: "pause", ACTIVE: "resume", DONE: "done"}[
            {"pause": PAUSED, "resume": ACTIVE, "done": DONE}[action]
        ]
        goal = goals.set_status(session_id, status)
        if goal is None:
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND, f"session has no goal: {session_id}")
        return {"session": session_id, "status": goal.status}
