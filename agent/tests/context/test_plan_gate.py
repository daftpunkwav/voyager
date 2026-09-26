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
    tool = plan_tools(gates, asker)["plan"]
    return gates, asker, tool.handler


async def test_inactive_gate_refuses_submission() -> None:
    gates, _, handler = _tool_with([])
    out = await handler(action="exit", plan="# plan")
    assert "未开启" in out
    assert gates.section_for("") == ""


async def test_approval_closes_gate_and_records_plan() -> None:
    gates, asker, handler = _tool_with(["批准执行"])
    gates.set("", True)
    out = await handler(action="exit", plan="# step 1")
    assert "批准" in out
    assert "# step 1" in out  # the plan text rides the result: it must stay
    # in the transcript for execution after the turn's history write-back
    gate = gates.for_session("")
    assert gate.active is False
    assert gate.plan == "# step 1"
    assert asker.asked[0].options == ("批准执行", "继续计划")


async def test_approval_persists_plan_into_instance_history() -> None:
    """The approved plan lands in the instance's cross-turn history (and the
    live transcript when one is open) so later turns can execute against it —
    gate.plan alone is in-memory and write-only."""
    from types import SimpleNamespace

    from agent.runtime.current import current_instance

    gates, _asker, handler = _tool_with(["批准执行"])
    gates.set("s1", True)
    inst = SimpleNamespace(session="s1", history=[], _turn_messages=[{"role": "user"}])
    token = current_instance.set(inst)
    try:
        await handler(action="exit", plan="# step 1\n# step 2")
    finally:
        current_instance.reset(token)
    assert len(inst.history) == 1
    assert inst.history[0]["role"] == "user"
    assert "【已批准计划】" in inst.history[0]["content"]
    assert "# step 2" in inst.history[0]["content"]
    # the live transcript gets its own copy (turn end may rebuild from it)
    assert inst._turn_messages[-1]["content"] == inst.history[0]["content"]


async def test_approval_without_instance_still_records_gate_plan() -> None:
    """No live instance (human capability path / assembly edge): approval must
    still close the gate and keep the plan — never crash."""
    from agent.runtime.current import current_instance

    token = current_instance.set(None)
    try:
        gates, _asker, handler = _tool_with(["批准执行"])
        gates.set("", True)  # no live instance: the session falls back to ""
        out = await handler(action="exit", plan="# plan x")
        assert "批准" in out
        assert gates.for_session("").plan == "# plan x"
    finally:
        current_instance.reset(token)


async def test_rejection_keeps_gate_open_with_feedback() -> None:
    gates, _asker, handler = _tool_with(["继续计划", "第一段太多风险"])
    gates.set("", True)
    out = await handler(action="exit", plan="# risky plan")
    assert "未批准" in out and "第一段太多风险" in out
    assert gates.for_session("").active is True  # still in review phase


async def test_timeout_keeps_gate_open_without_feedback() -> None:
    gates, _, handler = _tool_with([None])  # reviewer never answered
    gates.set("", True)
    out = await handler(action="exit", plan="# plan")
    assert "未批准" in out and "(无)" in out
    assert gates.for_session("").active is True


def test_section_only_while_active() -> None:
    gates = PlanGates()
    gates.set("s1", True)
    assert "plan-review phase" in gates.section_for("s1")
    assert gates.section_for("other") == ""  # unrelated sessions are unaffected
    gates.set("s1", False)
    assert gates.section_for("s1") == ""


async def test_empty_plan_submission_keeps_gate_open() -> None:
    """An active gate plus an empty plan text is a parameter error handled in
    the tool's own readable language: no reviewer round-trip is spent."""
    gates, asker, handler = _tool_with([])
    gates.set("", True)
    out = await handler(action="exit", plan="   ")
    assert "参数错误" in out and "不能为空" in out
    assert asker.asked == []  # never reached the reviewer
    assert gates.for_session("").active is True
