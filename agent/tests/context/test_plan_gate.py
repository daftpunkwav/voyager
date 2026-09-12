"""Plan review gate: the human toggles the review phase; while active the
system prompt carries the review section, and exit_plan_mode asks the human —
approval closes the gate, a rejection keeps it open with feedback."""

from __future__ import annotations

from agent.context.plan_gate import PlanGates
from agent.tools.interact.question_broker import AskUser, Question
from agent.tools.plan import plan_tools


class _FakeAsker(AskUser):
    """Scripted AskUser: pops queued answers; records asked prompts."""

    def __init__(self, answers: list) -> None:
        super().__init__(None)
        self._answers = list(answers)
        self.asked: list[Question] = []

    async def ask(self, q: Question, *, trace_id: str = ""):
        self.asked.append(q)
        return self._answers.pop(0) if self._answers else None


def _tool_with(answers: list):
    gates = PlanGates()
    asker = _FakeAsker(answers)
    tool = plan_tools(gates, asker)["exit_plan_mode"]
    return gates, asker, tool.handler


async def test_inactive_gate_refuses_submission() -> None:
    gates, _, handler = _tool_with([])
    out = await handler(plan="# plan")
    assert "未开启" in out
    assert gates.section_for("") == ""


async def test_approval_closes_gate_and_records_plan() -> None:
    gates, asker, handler = _tool_with(["批准执行"])
    gates.set("", True)
    out = await handler(plan="# step 1")
    assert "批准" in out
    assert "# step 1" in out  # the plan text rides the result: it must stay
    # in the transcript for execution after the turn's history write-back
    gate = gates.for_session("")
    assert gate.active is False
    assert gate.plan == "# step 1"
    assert asker.asked[0].options == ("批准执行", "继续计划")


async def test_rejection_keeps_gate_open_with_feedback() -> None:
    gates, _asker, handler = _tool_with(["继续计划", "第一段太多风险"])
    gates.set("", True)
    out = await handler(plan="# risky plan")
    assert "未批准" in out and "第一段太多风险" in out
    assert gates.for_session("").active is True  # still in review phase


async def test_timeout_keeps_gate_open_without_feedback() -> None:
    gates, _, handler = _tool_with([None])  # reviewer never answered
    gates.set("", True)
    out = await handler(plan="# plan")
    assert "未批准" in out and "(无)" in out
    assert gates.for_session("").active is True


def test_section_only_while_active() -> None:
    gates = PlanGates()
    gates.set("s1", True)
    assert "计划评审" in gates.section_for("s1")
    assert gates.section_for("other") == ""  # unrelated sessions are unaffected
    gates.set("s1", False)
    assert gates.section_for("s1") == ""
