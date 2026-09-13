"""GOT: graph-of-thoughts as angles -> aggregate -> refine.

The task is answered from M fixed angles (correctness / completeness /
risks / feasibility, cycled) in parallel; an aggregation completion merges
the angle outputs into one draft, resolving contradictions explicitly
instead of averaging them; a refinement pass checks the draft back against
the angle outputs and repairs what was lost. With a toolbelt the refined
draft is handed to the ReAct loop for execution; without one the refined
draft is delivered as-is (nothing user-facing is left to generate, so
there is no streaming pass).

Budget: one invocation-level ModeBudget across all phases; a phase gate
(token or rounds spent) collapses to the best-so-far result, so the
aggregation draft still ships.
"""

from __future__ import annotations

import asyncio
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
    budget_reason,
    noop_event,
    sys_message,
)
from agent.subagent.modes.react import run_step
from agent.subagent.modes.registry import register_mode
from agent.subagent.modes.streaming import run_phase

#: Angle count and the fixed angle menu (cycled when M exceeds the menu)
GOT_ANGLES = 4
_ANGLE_MENU = ("正确性与事实核查", "完整性与遗漏", "风险与反例", "可行性与成本")
#: Refinement passes after aggregation (bounded; skipped once out of budget)
GOT_REFINE_ROUNDS = 1

_ANGLE_PROMPT = "从「{angle}」的角度处理该任务,输出该角度下的结论或方案要点。不要调用工具。"
_AGGREGATE_PROMPT = (
    "上面是同一任务从不同角度的产出。把它们聚合为一致、完整的最终解答:"
    "冲突之处明确取舍并说明理由,互补之处合并,不要遗漏任何角度的关键信息。"
)
_REFINE_PROMPT = (
    "对照上面各角度的产出检查你的聚合稿:指出丢失或被扭曲的关键内容,"
    "并输出修订后的完整解答(不要只输出修改说明)。"
)


def _spent(limits: ModeLimits, budget: ModeBudget) -> bool:
    """Whether any invocation cap is spent (phase gates collapse the graph)."""
    return budget.over_token_budget() or budget.rounds_exhausted()


async def run_got(
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

    # Phase 1: M angle outputs, in parallel
    angles = [_ANGLE_MENU[i % len(_ANGLE_MENU)] for i in range(GOT_ANGLES)]
    angle_prompts = [[*sys_message(_ANGLE_PROMPT.format(angle=a)), *messages] for a in angles]
    outputs = await asyncio.gather(
        *(
            run_phase(llm=llm, messages=p, on_event=on_event, deadline=deadline, budget=budget)
            for p in angle_prompts
        )
    )
    angle_texts = [reply.text or "" for reply in outputs]
    await on_step(
        "llm",
        "got-angles",
        f"{GOT_ANGLES} 个角度完成:{'、'.join(angles)}",
        {"mode": "got", "angles": angles},
    )

    # Phase 2: aggregate (explicit conflict resolution, not averaging)
    if _spent(limits, budget):
        return _budget_report(limits, budget, draft=angle_texts[0])
    angle_block = "\n\n".join(f"【{angle}】\n{text}" for angle, text in zip(angles, angle_texts))
    aggregate = await run_phase(
        llm=llm,
        messages=[
            *messages,
            {"role": "user", "content": _AGGREGATE_PROMPT + "\n\n" + angle_block},
        ],
        on_event=on_event,
        deadline=deadline,
        budget=budget,
    )
    draft = aggregate.text or angle_texts[0]
    await on_step(
        "llm", "got-aggregate", (draft or "")[:120], {"mode": "got", "phase": "aggregate"}
    )

    # Phase 3: refine against the angle outputs (skipped when out of budget)
    for round_n in range(1, GOT_REFINE_ROUNDS + 1):
        if _spent(limits, budget):
            break
        refine = await run_phase(
            llm=llm,
            messages=[
                *messages,
                {"role": "user", "content": _AGGREGATE_PROMPT + "\n\n" + angle_block},
                {"role": "assistant", "content": draft},
                {"role": "user", "content": _REFINE_PROMPT},
            ],
            on_event=on_event,
            deadline=deadline,
            budget=budget,
        )
        if refine.text:
            draft = refine.text
        await on_step(
            "llm", f"got-refine-{round_n}", (draft or "")[:120], {"mode": "got", "phase": "refine"}
        )

    # With tools the draft is executed; without, the refined draft is the
    # answer (nothing user-facing is left to generate, so no streaming pass)
    if toolbelt is not None and belt is not None:
        messages.append({"role": "assistant", "content": draft})
        messages.append(
            {"role": "user", "content": "按上面的聚合解答执行该任务;需要外部信息就调用工具。"}
        )
        return await run_step(
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
            rounds=limits.max_rounds,
        )
    return draft


def _budget_report(limits: ModeLimits, budget: ModeBudget, draft: str) -> str:
    return f"[预算] 已达{budget_reason(limits, budget)},图搜索提前收尾。当前结果:{draft[:200]}"


__all__ = ["GOT_ANGLES", "GOT_REFINE_ROUNDS", "run_got"]

register_mode(Mode.GOT, run_got)
