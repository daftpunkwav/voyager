"""REFLEXION: a ReAct draft followed by one self-review completion that
revises it (falls back to the draft when the review is empty)."""

from __future__ import annotations

from typing import Any

from agent.context.compressor import COMPRESS_BUDGET
from agent.context.governor import ContextGovernor
from agent.contracts import ToolRunner
from agent.llm import LLMClient
from agent.subagent.modes.base import (
    DeltaCb,
    EventCb,
    Mode,
    ModeLimits,
    StepCb,
    noop_event,
    sys_message,
)
from agent.subagent.modes.react import run_react
from agent.subagent.modes.registry import register_mode


async def run_reflexion(
    llm: LLMClient,
    toolbelt: ToolRunner | None,
    messages: list[dict[str, Any]],
    limits: ModeLimits,
    on_step: StepCb,
    *,
    on_delta: DeltaCb | None = None,
    on_event: EventCb = noop_event,
    compress_budget: int = COMPRESS_BUDGET,
    governor: ContextGovernor | None = None,
) -> str:
    draft = await run_react(
        llm,
        toolbelt,
        messages,
        limits,
        on_step,
        on_delta=on_delta,
        on_event=on_event,
        compress_budget=compress_budget,
        governor=governor,
    )
    review = await llm.complete(
        [
            *messages,
            {"role": "assistant", "content": draft},
            *sys_message("审视上面的草稿:指出问题并给出修订版。"),
        ]
    )
    await on_step("llm", "reflexion", "自我审视并修订", {"mode": "reflexion"})
    return review.text or draft


__all__ = ["run_reflexion"]

register_mode(
    Mode.REFLEXION,
    lambda **kw: run_reflexion(
        kw["llm"],
        kw["toolbelt"],
        kw["messages"],
        kw["limits"],
        kw["on_step"],
        on_delta=kw["on_delta"],
        on_event=kw["on_event"],
        compress_budget=kw["compress_budget"],
        governor=kw["governor"],
    ),
)
