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
honest partial report instead of looping. Round exhaustion skips the
remaining steps but never the closing report: one grace completion to
report is part of winding down.
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

#: Replans permitted for one invocation (a revised plan after a failed step)
PLAN_MAX_REPLANS = 1


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
    conversational: bool = False,
) -> str:
    budget = ModeBudget(limits)
    belt = CountingToolbelt(toolbelt) if toolbelt is not None else None

    # Phase 1: plan
    plan_reply = await run_phase(
        llm=llm,
        messages=[
            *sys_message(render(P.modes.plan_execute.plan, max_steps=MAX_PLAN_STEPS)),
            *messages,
        ],
        on_event=on_event,
        deadline=deadline,
        round_n=1,
        budget=budget,
    )
    plan_text = plan_reply.text or ""
    steps = parse_steps(plan_text)[:MAX_PLAN_STEPS]
    await on_step("llm", "plan", plan_text[:120], {"mode": "plan_execute", "steps": len(steps)})
    # In-place append: the caller keeps a live reference to this list for
    # mid-turn snapshots and context-tool compaction - rebinding would detach
    # the plan entry and later compactions from it
    messages.append({"role": "assistant", "content": plan_text})

    # Phase 2: stepwise execution with bounded replanning
    outcomes: list[tuple[str, bool]] = []
    skipped: list[str] = []  # steps never attempted (budget spent)
    replans_left = PLAN_MAX_REPLANS
    index = 0
    while index < len(steps):
        if budget.over_token_budget() or budget.rounds_exhausted():
            skipped.extend(steps[index:])
            break
        step = steps[index]
        messages.append(
            {
                "role": "user",
                "content": render(
                    P.modes.step_instruction, index=index + 1, total=len(steps), step=step
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
        failed = looks_aborted(result)
        outcomes.append((step, not failed))
        await on_step(
            "llm",
            f"plan-step-{index + 1}",
            ("受阻" if failed else "完成") + ":" + step,
            {"mode": "plan_execute", "step": index + 1, "ok": not failed},
        )
        if failed and replans_left > 0 and index + 1 < len(steps):
            # A failed step with steps left: one bounded replan revises the
            # remaining work instead of grinding into the same wall
            replans_left -= 1
            messages.append({"role": "assistant", "content": result})
            replan_reply = await run_phase(
                llm=llm,
                messages=[
                    *messages,
                    {
                        "role": "user",
                        "content": render(
                            P.modes.plan_execute.replan,
                            remaining="; ".join(steps[index + 1 :]),
                        ),
                    },
                ],
                on_event=on_event,
                deadline=deadline,
                budget=budget,
            )
            new_steps = parse_steps(replan_reply.text or "")
            if new_steps:
                steps = steps[: index + 1] + new_steps[:MAX_PLAN_STEPS]
                messages.append({"role": "assistant", "content": replan_reply.text or ""})
                await on_step(
                    "llm",
                    "replan",
                    f"已修订剩余 {len(new_steps)} 步",
                    {"mode": "plan_execute", "replan": True},
                )
        index += 1

    # Phase 3: final report (streamed when the caller consumes deltas);
    # skipped only when the token budget is spent entirely - a
    # rounds-exhausted invocation can still afford its one closing completion
    if budget.over_token_budget() and limits.max_tokens > 0:
        done = sum(1 for _, ok in outcomes if ok)
        return render(
            P.modes.plan_execute.budget,
            reason=budget_reason(limits, budget),
            done=done,
            total=len(outcomes),
        )
    if skipped:
        # Skipped steps never reached the transcript: the report must be
        # told explicitly, or it would present them as silently done
        messages.append(
            {
                "role": "user",
                "content": render(P.modes.plan_execute.skipped, steps="; ".join(skipped)),
            }
        )
    messages.append(
        {
            "role": "user",
            "content": (
                P.modes.plan_execute.chat_report if conversational else P.modes.plan_execute.report
            ),
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
        "llm", "plan-report", (final.text or "")[:120], {"mode": "plan_execute", "phase": "report"}
    )
    return final.text or ""


__all__ = ["PLAN_MAX_REPLANS", "run_plan_execute"]

register_mode(Mode.PLAN_EXECUTE, run_plan_execute)
