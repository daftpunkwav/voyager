"""REFLEXION: attempt -> self-review -> retry with the lessons attached.

Attempt 1 runs the ReAct loop. A review completion then returns a verdict:
ADEQUATE (the draft stands) or REVISE plus concrete lessons (what failed,
what to do differently). A REVISE verdict appends the lessons to the
transcript as a user-role reflection entry and the next attempt runs with
them visible - verbal reinforcement across attempts, the loop Reflexion is
named for. An empty or unreadable review accepts the draft: a broken
reflection must not destroy a finished attempt.

Attempts are bounded (REFLEXION_MAX_ATTEMPTS) and share the invocation's
one ModeBudget; a spent cap skips the review and delivers the draft. The
final attempt's result is delivered as-is. The review instruction rides a
user-role message, not a mid-transcript system row: some gateways reject
system entries after the conversation head.
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
    noop_event,
)
from agent.subagent.modes.react import run_step
from agent.subagent.modes.registry import register_mode
from agent.subagent.modes.streaming import run_phase

#: Total attempts (first draft + bounded retries)
REFLEXION_MAX_ATTEMPTS = 2

_REVIEW_PROMPT = (
    "审视上面的草稿是否已经充分完成了任务。只输出以下两种格式之一:\n"
    "ADEQUATE:一句话说明为什么可以接受;\n"
    "REVISE:先指出具体问题,再列出下次尝试要怎么做(逐条)。\n"
    "不要调用工具。"
)


def _verdict(review: str) -> str:
    """ADEQUATE / REVISE / "" (unreadable); the marker must lead the reply so
    a review that merely mentions the words is not mistaken for a verdict."""
    head = (review or "").strip()[:16].upper()
    if head.startswith("ADEQUATE"):
        return "ADEQUATE"
    if head.startswith("REVISE"):
        return "REVISE"
    return ""


async def run_reflexion(
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
    draft = ""
    for attempt in range(1, REFLEXION_MAX_ATTEMPTS + 1):
        # Attempt: one bounded ReAct slice on the shared transcript (the
        # previous attempt's transcript and lessons stay visible)
        draft = await run_step(
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
            rounds=max(1, limits.max_rounds // REFLEXION_MAX_ATTEMPTS),
        )
        await on_step(
            "llm",
            f"reflexion-attempt-{attempt}",
            draft[:120],
            {"mode": "reflexion", "attempt": attempt},
        )
        if attempt == REFLEXION_MAX_ATTEMPTS:
            break  # last attempt: deliver as-is, no review spend
        if budget.over_token_budget() or budget.rounds_exhausted():
            break  # no budget for the review: the draft stands
        # Review: structured verdict (ADEQUATE ends the loop)
        review = await run_phase(
            llm=llm,
            messages=[
                *messages,
                {"role": "assistant", "content": draft},
                {"role": "user", "content": _REVIEW_PROMPT},
            ],
            on_event=on_event,
            deadline=deadline,
            budget=budget,
        )
        verdict = _verdict(review.text or "")
        await on_step(
            "llm",
            f"reflexion-review-{attempt}",
            (verdict or "无法判定") + ":" + (review.text or "")[:100],
            {"mode": "reflexion", "verdict": verdict or "unreadable"},
        )
        if verdict != "REVISE":
            break  # ADEQUATE or unreadable: the draft stands
        # Retry with the lessons visible; the reflection rides the transcript
        # as a user-role entry so the next attempt reads it as instruction
        messages.append({"role": "assistant", "content": draft})
        messages.append(
            {
                "role": "user",
                "content": f"【反思】上一次尝试未通过自我审视。{review.text}\n"
                "请根据以上反思重新完成任务。",
            }
        )
    return draft


__all__ = ["REFLEXION_MAX_ATTEMPTS", "run_reflexion"]

register_mode(Mode.REFLEXION, run_reflexion)
