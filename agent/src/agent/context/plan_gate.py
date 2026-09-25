"""Session-scoped plan gate: while active, the system prompt carries a
review-phase section (explore and design only, no side effects) and the model
can leave the phase only through plan(action=exit), which asks the human.

Pure state and prompt text. The toggle is human-side (a review gate must
stay under human control); the gate is in-memory interaction state — a
restart naturally ends any open review phase.
"""

from __future__ import annotations

from agent.prompts import P

# Prompt layer text lives in prompts/definitions/context.toml ([context.plan_gate]).
PLAN_SECTION_TITLE = P.context.plan_gate.title


class PlanGate:
    """One session's review-phase state."""

    def __init__(self) -> None:
        self.active = False
        self.plan = ""  # last approved plan text (empty until an approval)

    def section(self) -> str:
        """The prompt layer while active; empty otherwise."""
        return PLAN_SECTION_TITLE + P.context.plan_gate.body if self.active else ""


class PlanGates:
    """session id -> gate. Sessions without a gate are simply not in plan
    mode, so lookups on arbitrary session ids stay cheap."""

    def __init__(self) -> None:
        self._gates: dict[str, PlanGate] = {}

    def for_session(self, session: str) -> PlanGate:
        gate = self._gates.get(session)
        if gate is None:
            gate = self._gates[session] = PlanGate()
        return gate

    def set(self, session: str, enabled: bool) -> None:
        self.for_session(session).active = enabled

    def section_for(self, session: str) -> str:
        gate = self._gates.get(session)
        return gate.section() if gate is not None else ""


__all__ = ["PLAN_SECTION_TITLE", "PlanGate", "PlanGates"]
