"""Session-scoped plan gate: while active, the system prompt carries a
review-phase section (explore and design only, no side effects) and the model
can leave the phase only through exit_plan_mode, which asks the human.

Pure state and prompt text. The toggle is human-side (a review gate must
stay under human control); the gate is in-memory interaction state — a
restart naturally ends any open review phase.
"""

from __future__ import annotations

PLAN_SECTION_TITLE = "【计划模式】"
_PLAN_SECTION_BODY = (
    "你正处于计划评审阶段:先探索、阅读与设计,产出完整计划;"
    "不要执行任何写入、删除、发送或其他有副作用的操作。"
    "完成设计后,用 plan(action=exit) 提交计划全文,等待评审人批准。"
)


class PlanGate:
    """One session's review-phase state."""

    def __init__(self) -> None:
        self.active = False
        self.plan = ""  # last approved plan text (empty until an approval)

    def section(self) -> str:
        """The prompt layer while active; empty otherwise."""
        return PLAN_SECTION_TITLE + _PLAN_SECTION_BODY if self.active else ""


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
