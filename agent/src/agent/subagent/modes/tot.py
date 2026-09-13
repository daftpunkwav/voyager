"""TOT: tree-of-thoughts as generate -> evaluate -> expand -> select -> run.

Level 1: N candidate approaches are generated in parallel (each with its
rationale and key risk). A judge completion ranks them (JSON, parsed with a
deterministic fallback to the original order). Level 2: the top K approaches
are expanded into full drafts, again in parallel. A final judge picks the
winning draft; with a toolbelt the winner is handed to the ReAct loop for
execution (the tree reasons about the task, the tools do the work), without
one the winning draft is the answer.

Budget: the invocation's ModeLimits cover every phase (ModeBudget) - N-way
generation multiplies token spend, so between phases the tree collapses
gracefully to best-so-far instead of blowing the cap (token or rounds).
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

#: Level-1 breadth (candidate approaches) and the expansion width
TOT_BRANCHES = 3
TOT_KEEP = 2

_GENERATE_PROMPT = (
    "给出解决该任务的一种候选方案(第 {i}/{n} 路):方案本体、为什么可行、"
    "关键风险。简洁,不要调用工具。"
)
_JUDGE_PROMPT = (
    "下面是同一任务的 {n} 个候选方案(以 [A]/[B]/[C] 标注)。"
    '评估并排序,只输出一个 JSON 对象:{{"ranking": ["最佳方案字母", ...]}}。'
)
_EXPAND_PROMPT = "把方案 {letter} 展开为该任务的完整解答:直接给结果,不留方案框架。"
_PICK_PROMPT = (
    "下面是该任务的两个完整解答(以 [A]/[B] 标注)。选出更优的一个,"
    '只输出一个 JSON 对象:{"best": "字母"}。'
)


def _parse_ranking(text: str, width: int) -> list[int]:
    """Ranking as 0-based indices from the judge reply; a malformed reply
    degrades to the original order (generation order is a prior, not a
    verdict)."""
    from agent.context.editor import parse_plan

    plan = parse_plan(text or "")
    letters = plan.get("ranking") if isinstance(plan, dict) else None
    if not isinstance(letters, list):
        return list(range(width))
    order: list[int] = []
    for item in letters:
        if not isinstance(item, str):
            continue
        letter = item.strip().upper()[:1]
        if letter.isalpha() and ord(letter) - ord("A") < width:
            idx = ord(letter) - ord("A")
            if idx not in order:
                order.append(idx)
    return order + [i for i in range(width) if i not in order]


def _parse_best(text: str, width: int) -> int:
    from agent.context.editor import parse_plan

    plan = parse_plan(text or "")
    letter = plan.get("best") if isinstance(plan, dict) else None
    if isinstance(letter, str):
        idx = ord(letter.strip().upper()[:1]) - ord("A")
        if 0 <= idx < width:
            return idx
    return 0


def _spent(limits: ModeLimits, budget: ModeBudget) -> bool:
    """Whether any invocation cap is spent (phase gates collapse the tree)."""
    return budget.over_token_budget() or budget.rounds_exhausted()


async def run_tot(
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

    # Level 1: candidate approaches, in parallel
    prompts = [
        [
            *sys_message(_GENERATE_PROMPT.format(i=i + 1, n=TOT_BRANCHES)),
            *messages,
        ]
        for i in range(TOT_BRANCHES)
    ]
    candidates = await asyncio.gather(
        *(
            run_phase(llm=llm, messages=p, on_event=on_event, deadline=deadline, budget=budget)
            for p in prompts
        )
    )
    texts = [reply.text or "" for reply in candidates]
    await on_step(
        "llm",
        "tot-generate",
        f"{TOT_BRANCHES} 路候选完成",
        {"mode": "tot", "branches": TOT_BRANCHES},
    )

    # Judge: rank the candidates
    if _spent(limits, budget):
        return _budget_report(limits, budget, best=texts[0])
    letters = "\n\n".join(f"[{chr(ord('A') + i)}]\n{t}" for i, t in enumerate(texts))
    judge = await run_phase(
        llm=llm,
        messages=[
            *messages,
            {"role": "user", "content": _JUDGE_PROMPT.format(n=TOT_BRANCHES) + "\n\n" + letters},
        ],
        on_event=on_event,
        deadline=deadline,
        budget=budget,
    )
    order = _parse_ranking(judge.text or "", TOT_BRANCHES)
    await on_step(
        "llm",
        "tot-judge",
        f"排序:{[chr(ord('A') + i) for i in order]}",
        {"mode": "tot", "ranking": order},
    )

    # Level 2: expand the top K, in parallel
    if _spent(limits, budget):
        return _budget_report(limits, budget, best=texts[order[0]])
    expand_prompts = [
        [
            *sys_message(_EXPAND_PROMPT.format(letter=chr(ord("A") + i))),
            *messages,
            {"role": "assistant", "content": texts[i]},
        ]
        for i in order[:TOT_KEEP]
    ]
    drafts = await asyncio.gather(
        *(
            run_phase(llm=llm, messages=p, on_event=on_event, deadline=deadline, budget=budget)
            for p in expand_prompts
        )
    )
    draft_texts = [reply.text or "" for reply in drafts]
    await on_step("llm", "tot-expand", f"{len(draft_texts)} 个方案展开完成", {"mode": "tot"})

    # Final judge: pick the winner
    if _spent(limits, budget):
        return _budget_report(limits, budget, best=draft_texts[0])
    if len(draft_texts) > 1:
        pair = "\n\n".join(f"[{chr(ord('A') + i)}]\n{t}" for i, t in enumerate(draft_texts))
        pick = await run_phase(
            llm=llm,
            messages=[*messages, {"role": "user", "content": _PICK_PROMPT + "\n\n" + pair}],
            on_event=on_event,
            deadline=deadline,
            budget=budget,
        )
        winner = _parse_best(pick.text or "", len(draft_texts))
        await on_step("llm", "tot-pick", f"选定 {chr(ord('A') + winner)}", {"mode": "tot"})
    else:
        winner = 0
    best = draft_texts[winner]

    # With tools the winner runs (the reasoning tree plans, react executes);
    # without, the winning draft is the answer - streamed when possible
    if toolbelt is not None and belt is not None:
        messages.append({"role": "assistant", "content": best})
        messages.append(
            {"role": "user", "content": "按上面的选定方案执行该任务;需要外部信息就调用工具。"}
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
    messages.append({"role": "assistant", "content": best})
    final = await run_phase(
        llm=llm,
        messages=[*messages, {"role": "user", "content": "把选定方案整理为最终答案直接输出。"}],
        on_event=on_event,
        deadline=deadline,
        on_delta=on_delta,
        budget=budget,
    )
    return final.text or best


def _budget_report(limits: ModeLimits, budget: ModeBudget, best: str) -> str:
    return f"[预算] 已达{budget_reason(limits, budget)},树搜索提前收尾。当前最优:{best[:200]}"


__all__ = ["TOT_BRANCHES", "TOT_KEEP", "run_tot"]

register_mode(Mode.TOT, run_tot)
