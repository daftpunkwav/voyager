"""PLAN_EXECUTE: one planning completion (no tools) written back into the
transcript, then the ReAct loop executes it."""

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


async def run_plan_execute(
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
    plan = await llm.complete([*sys_message("先给出分步执行计划,不要调用工具。"), *messages])
    await on_step("llm", "plan", (plan.text or "")[:120], {"mode": "plan"})
    # In-place append: the caller (instance) keeps a live reference to this
    # list for mid-turn snapshots and context-tool compaction - rebinding
    # would detach the plan entry and later compactions from it
    messages.append({"role": "assistant", "content": plan.text or ""})
    return await run_react(
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


__all__ = ["run_plan_execute"]

register_mode(
    Mode.PLAN_EXECUTE,
    lambda **kw: run_plan_execute(
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
