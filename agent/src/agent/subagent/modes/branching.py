"""Multi-way generation shared by ToT and GoT: run N candidate completions
in parallel, then one merge completion (select-best or aggregate)."""

from __future__ import annotations

import asyncio
from typing import Any

from agent.llm import LLMClient
from agent.subagent.modes.base import StepCb, sys_message


async def branch(
    llm: LLMClient,
    messages: list[dict[str, Any]],
    on_step: StepCb,
    *,
    branches: int,
    joint: bool,
) -> str:
    """ToT: generate candidates and pick the best; GoT: produce from multiple
    angles then aggregate."""
    hint = "从不同来源/角度各自作答,最后再合并。" if joint else "给出一种候选解答。"
    prompts = [[*sys_message(f"{hint}(第 {i + 1} 路)"), *messages] for i in range(branches)]
    candidates = await asyncio.gather(*(llm.complete(p) for p in prompts))
    texts = [c.text or "" for c in candidates]
    await on_step("llm", "branch", f"{branches} 路产出完成", {"branches": branches, "joint": joint})
    merge_prompt = (
        "把上面几路产出合并为一致、完整的最终答案。"
        if joint
        else "评估上面几个候选,选出最优并润色为最终答案。"
    )
    final = await llm.complete(
        [
            *messages,
            *[
                {"role": "assistant", "content": t, "name": f"branch-{i}"}
                for i, t in enumerate(texts)
            ],
            *sys_message(merge_prompt),
        ]
    )
    return final.text or texts[0]


__all__ = ["branch"]
