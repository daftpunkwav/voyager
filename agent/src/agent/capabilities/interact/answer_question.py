"""answer_question capability: deliver the user's answer back to a pending
AskUser request.

Human-only by direction (human -> agent reply channel); the agent asks via
the ask_user tool. See the parity exception list.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="answer_question",
        description="Deliver the answer back to a pending AskUser request",
    )
    def answer_question(question_id: str, value) -> dict:
        return {"matched": deps.asker.answer(question_id, value)}
