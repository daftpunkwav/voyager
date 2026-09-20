"""Plan tool group: the agent's plan-gate surface in one tool (status /
write / enter / exit) plus the goal tools and the scratchpad. Zero-logic
aggregation."""

from __future__ import annotations

from agent.context.plan_gate import PlanGates
from agent.tools.core.base import AgentTool
from agent.tools.interact.question_broker import AskUser
from agent.tools.plan.goal_read import goal_read_tool
from agent.tools.plan.goal_write import goal_write_tool
from agent.tools.plan.plan_ops import plan_enter, plan_status, plan_submit, plan_write
from agent.tools.plan.scratchpad import scratchpad_tool

__all__ = ["goal_tools", "plan_tools", "scratchpad_tool"]


def plan_tools(gates: PlanGates, asker: AskUser) -> dict[str, AgentTool]:
    async def plan(action: str = "status", plan: str = "") -> dict | str:
        from agent.runtime.current import current_instance

        inst = current_instance.get()
        session = inst.session if inst is not None else ""
        if action == "status":
            return plan_status(gates, session)
        if action == "write":
            return plan_write(gates, session, plan)
        if action == "enter":
            return plan_enter(gates, session)
        if action == "exit":
            return await plan_submit(gates, asker, plan)
        return f"[参数错误] 未知 action: {action}(可选 status/write/enter/exit)"

    tool = AgentTool(
        name="plan",
        description=(
            "计划评审门,action: status(查看门状态与草稿)/"
            " write(plan,保存计划草稿,不提交)/ enter(进入计划模式,只做探索与设计)/"
            " exit(plan 提交计划全文,等待评审人批准或打回;批准后退出计划模式,"
            "打回时带反馈继续修订)"
        ),
        handler=plan,
        schema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "write", "enter", "exit"],
                    "description": "status 查看 / write 存草稿 / enter 进入计划模式 / exit 提交评审",
                },
                "plan": {"type": "string", "description": "write/exit 的完整计划(markdown)"},
            },
        },
        dimension="none",
        write=False,
        concurrent_safe=False,
    )
    return {tool.name: tool}


def goal_tools(goals) -> dict[str, AgentTool]:
    goal_read = goal_read_tool(goals)
    goal_write = goal_write_tool(goals)
    return {goal_read.name: goal_read, goal_write.name: goal_write}
