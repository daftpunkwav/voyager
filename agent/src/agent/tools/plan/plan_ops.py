"""Plan-gate operations shared by the plan capability and the plan tool.

One gate per session: while active, the system prompt carries the planning
section and the session stays in design-only mode. Actions:
    status — gate state (+ last approved plan text)
    write  — store/replace the draft plan text without submitting
    enter  — turn the gate on (both sides may self-limit)
    exit   — asymmetric by design (interaction invariant, not permission):
             the HUMAN path simply turns the gate off (capability); the AGENT
             path submits the plan for human review through the ask channel
             and leaves plan mode only on approval (plan_submit).
"""

from __future__ import annotations

from agent.context.plan_gate import PlanGate, PlanGates
from agent.runtime.current import current_instance
from agent.tools.interact.question_broker import AskUser, Question

_APPROVE = "批准执行"
_KEEP_PLANNING = "继续计划"
_TIMEOUT_S = 600.0
_APPROVED_MARK = "【已批准计划】"


def _gate(gates: PlanGates, session: str) -> PlanGate:
    return gates.for_session(session)


def plan_status(gates: PlanGates, session: str) -> dict:
    gate = _gate(gates, session)
    return {
        "session_id": session,
        "plan_mode": gate.active,
        "draft": gate.plan,
    }


def plan_enter(gates: PlanGates, session: str) -> dict:
    gates.set(session, True)
    return {"session_id": session, "plan_mode": True}


def plan_write(gates: PlanGates, session: str, plan: str) -> dict:
    body = str(plan or "").strip()
    if not body:
        from platform_contracts import ErrorSuffix, ServiceError

        raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "plan must not be empty")
    gate = _gate(gates, session)
    gate.plan = body
    return {"session_id": session, "stored_chars": len(body)}


def plan_exit(gates: PlanGates, session: str) -> dict:
    """Human exit: leave plan mode directly (the gate is the human's to
    close without review)."""
    gates.set(session, False)
    return {"session_id": session, "plan_mode": False}


async def plan_submit(gates: PlanGates, asker: AskUser, plan: str) -> str:
    """Agent exit: submit the plan full text for human review and leave plan
    mode on approval (a rejected plan keeps the gate open with the reviewer's
    feedback). An approved plan is echoed back in full as the tool result so
    execution can follow it step by step."""
    inst = current_instance.get()
    session = inst.session if inst is not None else ""
    gate = gates.for_session(session)
    if not gate.active:
        return "[未开启] 当前会话不在计划模式,无需提交计划"
    body = str(plan or "").strip()
    if not body:
        return "[参数错误] plan 不能为空(请提交计划全文)"
    verdict = await asker.ask(
        Question(
            prompt="计划评审:是否批准按此计划执行?",
            kind="choice",
            options=(_APPROVE, _KEEP_PLANNING),
            timeout_s=_TIMEOUT_S,
        )
    )
    if verdict == _APPROVE:
        gate.active = False
        gate.plan = body
        # The plan must survive the turn: the tool result carries it through
        # the rest of this turn (the submission lives in tool_call arguments,
        # which the turn-end history write-back drops), and the history
        # entry keeps it available to every later turn. Both surfaces get
        # the entry because the turn end either keeps history as-is (normal
        # path) or rebuilds it from the live messages (summary path).
        if inst is not None:
            entry = {"role": "user", "content": f"{_APPROVED_MARK}\n{body}"}
            inst.history.append(entry)
            if inst._turn_messages is not None:
                inst._turn_messages.append(dict(entry))
        return (
            "计划已获批准,已退出计划模式。计划全文如下,请从第一步开始严格按计划执行"
            "(后续轮次对照此计划逐项推进,已完成的步骤不再重复):\n\n"
            f"{body}"
        )
    feedback = ""
    if verdict == _KEEP_PLANNING:
        answer = await asker.ask(
            Question(
                prompt="请输入对计划的修订反馈:",
                kind="text",
                timeout_s=_TIMEOUT_S,
            )
        )
        feedback = str(answer or "").strip()
    return f"评审人未批准,计划模式保持开启。反馈:{feedback or '(无)'};请修订后重新提交。"


__all__ = [
    "plan_enter",
    "plan_exit",
    "plan_status",
    "plan_submit",
    "plan_write",
]
