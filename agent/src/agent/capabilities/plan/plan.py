"""plan capability: the human REST surface for the session plan gate — one
action parameter covers status/write/enter/exit.

The agent's plan tool binds the same operations (tools/plan/plan_ops.py) with
one deliberate asymmetry: the agent's exit submits the plan for human review,
the human exit closes the gate directly. That is an interaction invariant of
the review gate (the gate decides when the agent may act), not a permission.

 goal_manage stays a separate capability in this group (aggregated with the
team domain per the design)."""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.tools.plan.plan_ops import plan_enter, plan_exit, plan_status, plan_write


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="plan",
        description=(
            "Session plan review gate: action status (gate state + draft),"
            " write (plan text draft), enter (turn the gate on), exit (turn it"
            " off; the agent side goes through human review instead)"
        ),
    )
    def plan(action: str = "status", session_id: str = "", plan: str = "") -> dict:
        assert deps.plan_gates is not None, "plan gates not wired at assembly"
        gates = deps.plan_gates
        if action == "status":
            return plan_status(gates, session_id)
        if action == "write":
            return plan_write(gates, session_id, plan)
        if action == "enter":
            return plan_enter(gates, session_id)
        if action == "exit":
            return plan_exit(gates, session_id)
        raise ServiceError(
            "agent",
            ErrorSuffix.INVALID_INPUT,
            f"unknown action: {action!r}",
            hint="valid actions: status/write/enter/exit",
        )
