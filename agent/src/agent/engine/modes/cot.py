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
the token budget is spent - a partial answer with step status beats
silence. Round exhaustion skips the remaining steps but never the closing
summary: one grace completion to report is part of winding down.
"""

from __future__ import annotations

from typing import Any

from agent.context.compressor import COMPRESS_BUDGET
from agent.context.governor import ContextGovernor
from agent.contracts import ToolRunner
from agent.engine.modes.base import (
    MAX_PLAN_STEPS,
    CountingToolbelt,
    DeltaCb,
    EventCb,
    Mode,
    ModeBudget,
    ModeLimits,
    StepCb,
    budget_reason,
    looks_aborted,
    noop_event,
    parse_steps,
    sys_message,
)
from agent.engine.modes.react import run_step
from agent.engine.modes.registry import register_mode
from agent.engine.modes.streaming import run_phase
from agent.llm import LLMClient
from agent.prompts import P, render
from agent.runtime.deadline import Deadline


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
    conversational: bool = False,
) -> str:
    budget = ModeBudget(limits)
    belt = CountingToolbelt(toolbelt) if toolbelt is not None else None

    # Phase 1: decompose into an inspectable plan
    plan_reply = await run_phase(
        llm=llm,
        messages=[*sys_message(render(P.modes.cot.plan, max_steps=MAX_PLAN_STEPS)), *messages],
        on_event=on_event,
        deadline=deadline,
        round_n=1,
        budget=budget,
    )
    steps = parse_steps(plan_reply.text or "")[:MAX_PLAN_STEPS]
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
        if budget.over_token_budget() or budget.rounds_exhausted():
            outcomes.append((f"跳过:{step}", False))
            continue
        messages.append(
            {
                "role": "user",
                "content": render(
                    P.modes.step_instruction, index=index, total=len(steps), step=step
                ),
            }
        )
        result = await run_step(
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
    # only when the token budget is spent entirely - a rounds-exhausted
    # invocation can still afford its one closing completion
    if budget.over_token_budget() and limits.max_tokens > 0:
        done = sum(1 for _, ok in outcomes if ok)
        return render(
            P.modes.cot.budget,
            reason=budget_reason(limits, budget),
            done=done,
            total=len(outcomes),
        )
    skipped = [
        entry.removeprefix("跳过:")
        for entry, ok in outcomes
        if not ok and entry.startswith("跳过:")
    ]
    if skipped:
        # Skipped steps never reached the transcript: the synthesis must be
        # told explicitly, or it would report them as silently done
        messages.append(
            {
                "role": "user",
                "content": render(P.modes.cot.skipped, steps="; ".join(skipped)),
            }
        )
    messages.append(
        {
            "role": "user",
            "content": P.modes.cot.chat_synthesis if conversational else P.modes.cot.synthesis,
        }
    )
    final = await run_phase(
        llm=llm,
        messages=messages,
        on_event=on_event,
        deadline=deadline,
        on_delta=on_delta,
        budget=budget,
    )
    await on_step(
        "llm",
        "cot-synthesis",
        (final.text or "")[:120],
        {"mode": "cot", "phase": "synthesis"},
    )
    return final.text or ""


__all__ = ["run_cot"]

register_mode(Mode.COT, run_cot)
