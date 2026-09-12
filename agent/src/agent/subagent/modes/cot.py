"""COT: chain-of-thought = DIRECT with a "reason step by step first" prefix."""

from __future__ import annotations

from typing import Any

from agent.llm import LLMClient
from agent.subagent.modes.base import EventCb, Mode, noop_event, sys_message
from agent.subagent.modes.direct import run_direct
from agent.subagent.modes.registry import register_mode


async def run_cot(
    llm: LLMClient, messages: list[dict[str, Any]], *, on_event: EventCb = noop_event
) -> str:
    return await run_direct(
        llm, [*sys_message("请先逐步推理,再给出结论。"), *messages], on_event=on_event
    )


__all__ = ["run_cot"]

register_mode(
    Mode.COT,
    lambda **kw: run_cot(kw["llm"], kw["messages"], on_event=kw["on_event"]),
)
