"""DIRECT: a single completion round (streams when the llm supports it)."""

from __future__ import annotations

from typing import Any

from platform_contracts import RuntimeEvent

from agent.engine.modes.base import DeltaCb, EventCb, Mode, noop_event
from agent.engine.modes.registry import register_mode
from agent.engine.modes.streaming import complete_streaming, delta_timer
from agent.llm import LLMClient
from agent.runtime.deadline import Deadline


async def run_direct(
    llm: LLMClient,
    messages: list[dict[str, Any]],
    *,
    on_delta: DeltaCb | None = None,
    on_event: EventCb = noop_event,
    deadline: Deadline | None = None,
) -> str:
    round_delta = None
    if on_delta is not None:
        round_delta, _first = delta_timer(on_delta, on_event=on_event, round_n=1)
    await on_event(RuntimeEvent.LLM_STARTED, round=1, streaming=on_delta is not None)
    if deadline is not None:
        reply = await deadline.run_round(
            lambda: complete_streaming(llm, messages, None, round_delta, round_n=1)
        )
    else:
        reply = await complete_streaming(llm, messages, None, round_delta, round_n=1)
    await on_event(
        RuntimeEvent.LLM_COMPLETED,
        round=1,
        input_tokens=reply.usage.input_tokens,
        output_tokens=reply.usage.output_tokens,
        degraded=bool(reply.degraded),
        overflow=bool(reply.overflow),
    )
    return reply.text or ""


__all__ = ["run_direct"]

register_mode(
    Mode.DIRECT,
    lambda **kw: run_direct(
        kw["llm"],
        kw["messages"],
        on_delta=kw["on_delta"],
        on_event=kw["on_event"],
        deadline=kw["deadline"],
    ),
)
