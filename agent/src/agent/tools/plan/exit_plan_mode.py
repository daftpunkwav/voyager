"""exit_plan_mode tool: submit the plan for human review and leave plan mode
on approval (rejected plans keep the gate open with the reviewer's feedback).
An approved plan is echoed back in full as the tool result so execution can
follow it step by step."""

from __future__ import annotations

from agent.context.plan_gate import PlanGates
from agent.runtime.current import current_instance
from agent.tools.core.base import AgentTool
from agent.tools.interact.question_broker import AskUser, Question

_APPROVE = "批准执行"
_KEEP_PLANNING = "继续计划"
_TIMEOUT_S = 600.0
_APPROVED_MARK = "【已批准计划】"


def exit_plan_mode_tool(gates: PlanGates, asker: AskUser) -> AgentTool:
    async def exit_plan_mode(plan: str = "") -> str:
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

    return AgentTool(
        name="exit_plan_mode",
        description=(
            "计划评审阶段专用:提交计划全文,等待评审人批准或打回;"
            "批准后退出计划模式,打回时带反馈继续修订"
        ),
        handler=exit_plan_mode,
        dimension="none",
        write=False,
        concurrent_safe=False,
        schema={
            "type": "object",
            "properties": {"plan": {"type": "string", "description": "完整计划(markdown)"}},
            "required": ["plan"],
        },
    )


__all__ = ["exit_plan_mode_tool"]
