"""COT: chain-of-thought as a stepwise worker, not a one-shot hint.

Phases:
1. decompose - one tool-free completion turns the task into an explicit
   numbered reasoning plan (the "reason step by step" discipline, made
   inspectable instead of implicit);
2. execute - each step runs as its own bounded slice on the shared
   transcript (tool access via the ReAct loop when a toolbelt is granted),
   with the step outcome recorded before the next one starts;
3. synthesize - one completion delivers the final answer from the step
   results, streaming to the user when the caller consumes deltas.

The invocation's ModeLimits are ONE budget across all phases (ModeBudget):
a step slice gets what is left, a failed or aborted step is recorded and
skipped rather than silently dropped, and the synthesis always runs unless
the token budget is spent - a partial answer with step status beats silence.
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
from agent.subagent.modes.react import run_react
from agent.subagent.modes.registry import register_mode
from agent.subagent.modes.streaming import run_phase

#: Rounds a step slice may use (tool work inside a step needs more than one)
COT_STEP_ROUNDS = 4

#: Upper bound on planned steps: a runaway list is truncated, not followed
COT_MAX_STEPS = 8

_PLAN_PROMPT = (
    "请先逐步推理,再给出结论。把完成该任务需要的推理过程拆成编号步骤"
    f"(每行一步,动词开头,最多 {COT_MAX_STEPS} 步),不要调用工具。"
)

_SYNTHESIS_PROMPT = (
    "以上按步骤完成了任务。综合所有步骤的结果给出最终答案:直接回答任务本身,标注未完成的步骤(如有)。"
)


async def _execute_step(
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
    """One step on the shared transcript: a bounded ReAct slice when tools
    are granted, a plain completion otherwise. Returns the step result text."""
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
        "cot-step",
        llm=llm,
        messages=messages,
        on_event=on_event,
        deadline=deadline,
    )
    budget.add_usage(reply.usage)
    budget.add_rounds(1)
    return reply.text or ""


async def run_cot(
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

    # Phase 1: decompose into an inspectable plan
    plan_reply = await run_phase(
        "cot-plan",
        llm=llm,
        messages=[*sys_message(_PLAN_PROMPT), *messages],
        on_event=on_event,
        deadline=deadline,
        round_n=1,
    )
    budget.add_usage(plan_reply.usage)
    budget.add_rounds(1)
    steps = parse_steps(plan_reply.text or "")[:COT_MAX_STEPS]
    await on_step(
        "llm",
        "cot-plan",
        (plan_reply.text or "")[:120],
        {"mode": "cot", "steps": len(steps)},
    )
    # The plan rides the transcript so later phases (and the transcript
    # reader) see what was planned; in-place append keeps the caller's
    # live reference for mid-turn snapshots
    messages.append({"role": "assistant", "content": plan_reply.text or ""})

    # Phase 2: execute the steps, budget-permitting
    outcomes: list[tuple[str, bool]] = []  # (step, ok)
    for index, step in enumerate(steps, start=1):
        if budget.over_token_budget():
            outcomes.append((f"跳过:{step}", False))
            continue
        messages.append(
            {
                "role": "user",
                "content": f"【步骤 {index}/{len(steps)}】{step}\n完成本步骤;需要外部信息就调用工具。",
            }
        )
        result = await _execute_step(
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
        ok = not looks_aborted(result)
        if not ok:
            # The slice's abort report must not masquerade as the step's
            # outcome: keep it as an assistant note so the transcript stays
            # coherent and the synthesis knows the step failed
            messages.append({"role": "assistant", "content": result})
        outcomes.append((step, ok))
        await on_step(
            "llm",
            f"cot-step-{index}",
            ("完成" if ok else "受阻") + ":" + step,
            {"mode": "cot", "step": index, "ok": ok},
        )

    # Phase 3: synthesize (streamed when the caller consumes deltas); skipped
    # only when the invocation's token budget is spent entirely
    if budget.over_token_budget() and limits.max_tokens > 0:
        done = sum(1 for _, ok in outcomes if ok)
        return (
            f"[预算] 已达 token 上限({limits.max_tokens}),链式推理中途收尾:"
            f"{done}/{len(outcomes)} 步完成。可在设置提高 agent.rounds.max_tokens 后继续。"
        )
    messages.append({"role": "user", "content": _SYNTHESIS_PROMPT})
    final = await run_phase(
        "cot-synthesis",
        llm=llm,
        messages=messages,
        on_event=on_event,
        deadline=deadline,
        on_delta=on_delta,
    )
    budget.add_usage(final.usage)
    await on_step(
        "llm",
        "cot-synthesis",
        (final.text or "")[:120],
        {"mode": "cot", "phase": "synthesis"},
    )
    return final.text or ""


__all__ = ["COT_MAX_STEPS", "COT_STEP_ROUNDS", "run_cot"]

register_mode(Mode.COT, run_cot)
