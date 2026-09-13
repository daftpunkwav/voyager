"""PLAN_EXECUTE: plan -> stepwise execution -> replan-on-failure -> report.

Phases:
1. plan - one tool-free completion produces numbered steps (parse_steps);
   the plan rides the transcript so execution and later phases see it;
2. execute - each step runs as its own bounded ReAct slice on the shared
   transcript (tools granted) or one completion (no tools), and its outcome
   is recorded; a failed step triggers a bounded replan that revises the
   remaining steps against what actually happened instead of grinding on;
3. report - one completion delivers the final answer with per-step status,
   streamed when the caller consumes deltas.

The invocation's ModeLimits are ONE budget across all phases (ModeBudget);
replans are bounded (PLAN_MAX_REPLANS) so a failing task winds down with an
honest partial report instead of looping.
"""

from __future__ import annotations

from typing import Any

from agent.context.compressor import COMPRESS_BUDGET
from agent.context.governor import ContextGovernor
from agent.contracts import ToolRunner
from agent.llm import LLMClient
from agent.runtime.deadline import Deadline
from agent.subagent.modes.base import (
    CountingToolbelt,
    DeltaCb,
    EventCb,
    Mode,
    ModeBudget,
    ModeLimits,
    StepCb,
    counting_step,
    looks_aborted,
    noop_event,
    parse_steps,
    sys_message,
)
from agent.subagent.modes.cot import COT_MAX_STEPS, COT_STEP_ROUNDS
from agent.subagent.modes.react import run_react
from agent.subagent.modes.registry import register_mode
from agent.subagent.modes.streaming import run_phase

#: Replans permitted for one invocation (a revised plan after a failed step)
PLAN_MAX_REPLANS = 1

_PLAN_PROMPT = (
    "先给出分步执行计划,不要调用工具:编号列出为完成任务要做的每一步"
    f"(每行一步,动词开头,最多 {COT_MAX_STEPS} 步),最后给出完成判定。"
)
_REPLAN_PROMPT = (
    "上面的步骤执行受阻。根据已发生的情况修订剩余步骤:"
    "编号列出新的步骤(已完成的不必重做),必要时改变方法。不要调用工具。"
)
_REPORT_PROMPT = (
    "任务执行结束。综合以上过程给出最终答案:直接回答任务本身,"
    "并简要标注各步骤的完成情况(如有未完成项)。"
)


async def _run_step(
    *,
    llm: LLMClient,
    toolbelt: ToolRunner | None,
    messages: list[dict[str, Any]],
    on_step: StepCb,
    on_event: EventCb,
    continue_if_idle: bool,
    compress_budget: int,
    governor: ContextGovernor | None,
    deadline: Deadline | None,
    budget: ModeBudget,
    belt: CountingToolbelt | None,
) -> str:
    """One step: a bounded ReAct slice (tools granted) or one completion."""
    if governor is not None:
        await governor.enforce(messages)
    if toolbelt is not None and belt is not None:
        before_calls = belt.calls
        result = await run_react(
            llm,
            belt,
            messages,
            budget.slice(rounds=COT_STEP_ROUNDS),
            counting_step(on_step, budget),
            on_event=on_event,
            continue_if_idle=continue_if_idle,
            compress_budget=compress_budget,
            governor=governor,
            deadline=deadline,
        )
        budget.add_tool_calls(belt.calls - before_calls)
        return result
    reply = await run_phase(
        "plan-step",
        llm=llm,
        messages=messages,
        on_event=on_event,
        deadline=deadline,
    )
    budget.add_usage(reply.usage)
    budget.add_rounds(1)
    return reply.text or ""


async def run_plan_execute(
    llm: LLMClient,
    toolbelt: ToolRunner | None,
    messages: list[dict[str, Any]],
    limits: ModeLimits,
    on_step: StepCb,
    *,
    on_delta: DeltaCb | None = None,
    on_event: EventCb = noop_event,
    continue_if_idle: bool = False,
    compress_budget: int = COMPRESS_BUDGET,
    governor: ContextGovernor | None = None,
    deadline: Deadline | None = None,
) -> str:
    budget = ModeBudget(limits)
    belt = CountingToolbelt(toolbelt) if toolbelt is not None else None

    # Phase 1: plan
    plan_reply = await run_phase(
        "plan",
        llm=llm,
        messages=[*sys_message(_PLAN_PROMPT), *messages],
        on_event=on_event,
        deadline=deadline,
        round_n=1,
    )
    budget.add_usage(plan_reply.usage)
    budget.add_rounds(1)
    plan_text = plan_reply.text or ""
    steps = parse_steps(plan_text)[:COT_MAX_STEPS]
    await on_step("llm", "plan", plan_text[:120], {"mode": "plan_execute", "steps": len(steps)})
    # In-place append: the caller keeps a live reference to this list for
    # mid-turn snapshots and context-tool compaction - rebinding would detach
    # the plan entry and later compactions from it
    messages.append({"role": "assistant", "content": plan_text})

    # Phase 2: stepwise execution with bounded replanning
    outcomes: list[tuple[str, bool]] = []
    replans_left = PLAN_MAX_REPLANS
    index = 0
    while index < len(steps):
        if budget.over_token_budget():
            outcomes.extend((s, False) for s in steps[index:])
            break
        step = steps[index]
        messages.append(
            {
                "role": "user",
                "content": f"【步骤 {index + 1}/{len(steps)}】{step}\n完成本步骤;需要外部信息就调用工具。",
            }
        )
        result = await _run_step(
            llm=llm,
            toolbelt=toolbelt,
            messages=messages,
            on_step=on_step,
            on_event=on_event,
            continue_if_idle=continue_if_idle,
            compress_budget=compress_budget,
            governor=governor,
            deadline=deadline,
            budget=budget,
            belt=belt,
        )
        outcomes.append((step, not looks_aborted(result)))
        await on_step(
            "llm",
            f"plan-step-{index + 1}",
            ("完成" if not looks_aborted(result) else "受阻") + ":" + step,
            {"mode": "plan_execute", "step": index + 1, "ok": not looks_aborted(result)},
        )
        if looks_aborted(result) and replans_left > 0 and index + 1 < len(steps):
            # A failed step with steps left: one bounded replan revises the
            # remaining work instead of grinding into the same wall
            replans_left -= 1
            budget.add_rounds(1)
            messages.append({"role": "assistant", "content": result})
            replan_reply = await run_phase(
                "replan",
                llm=llm,
                messages=[
                    *messages,
                    {
                        "role": "user",
                        "content": _REPLAN_PROMPT
                        + f"\n(剩余未执行步骤:{'; '.join(steps[index + 1 :])})",
                    },
                ],
                on_event=on_event,
                deadline=deadline,
            )
            budget.add_usage(replan_reply.usage)
            new_steps = parse_steps(replan_reply.text or "")
            if new_steps:
                steps = steps[: index + 1] + new_steps[:COT_MAX_STEPS]
                messages.append({"role": "assistant", "content": replan_reply.text or ""})
                await on_step(
                    "llm",
                    "replan",
                    f"已修订剩余 {len(new_steps)} 步",
                    {"mode": "plan_execute", "replan": True},
                )
        index += 1

    # Phase 3: final report (streamed when the caller consumes deltas)
    if budget.over_token_budget() and limits.max_tokens > 0:
        done = sum(1 for _, ok in outcomes if ok)
        return (
            f"[预算] 已达 token 上限({limits.max_tokens}),计划执行中途收尾:"
            f"{done}/{len(outcomes)} 步完成。可在设置提高 agent.rounds.max_tokens 后继续。"
        )
    messages.append({"role": "user", "content": _REPORT_PROMPT})
    final = await run_phase(
        "plan-report",
        llm=llm,
        messages=messages,
        on_event=on_event,
        deadline=deadline,
        on_delta=on_delta,
    )
    budget.add_usage(final.usage)
    await on_step(
        "llm", "plan-report", (final.text or "")[:120], {"mode": "plan_execute", "phase": "report"}
    )
    return final.text or ""


__all__ = ["PLAN_MAX_REPLANS", "run_plan_execute"]

register_mode(Mode.PLAN_EXECUTE, run_plan_execute)
