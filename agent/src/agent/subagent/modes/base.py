"""Mode vocabulary, callback contracts, shared step helpers and the run_mode
dispatcher.

The seven strategies live one per file (react / plan_execute / cot / tot /
got / reflexion / direct); each registers its runner in modes/registry.py at
import time, so this base never imports the mode modules (no cycle) and
run_mode dispatches through the registry. Rounds and tool calls are two
independent caps (ModeLimits); hitting either stops gracefully with an
explanation of how to raise it.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from agent.context.compressor import COMPRESS_BUDGET
from agent.context.governor import ContextGovernor
from agent.contracts import ToolRunner
from agent.llm import LLMClient, ToolCall
from agent.runtime.deadline import Deadline
from agent.subagent.modes.registry import runner_for


class Mode(str, Enum):
    REACT = "react"
    PLAN_EXECUTE = "plan_execute"
    COT = "cot"
    TOT = "tot"
    GOT = "got"
    REFLEXION = "reflexion"
    DIRECT = "direct"


@dataclass(frozen=True)
class ModeLimits:
    max_rounds: int = 20
    max_tool_calls: int = 40
    #: Per-invocation token budget (input+output); 0 = unlimited. Hitting it
    #: winds the mode down with a partial-result report, like the round cap.
    max_tokens: int = 0


StepCb = Callable[[str, str, str, dict[str, Any]], Awaitable[None]]  # (kind, name, summary, detail)
DeltaCb = Callable[[int, str], Awaitable[None]]  # (round, delta text)
#: Lifecycle event sink: (RuntimeEvent type, **payload). The instance binds
#: it to RuntimeEvents.emit with its run context; modes never see the bus.
EventCb = Callable[..., Awaitable[None]]

#: Cap on serialized tool arguments kept in a step detail (characters).
_MAX_DETAIL_ARGS_CHARS = 2000


async def noop_step(kind: str, name: str, summary: str, detail: dict[str, Any]) -> None:
    return None


async def noop_event(type_: str, **payload: Any) -> None:
    return None


def sys_message(content: str) -> list[dict[str, Any]]:
    return [{"role": "system", "content": content}]


def capped_args(arguments: Any) -> str:
    """Tool arguments as compact JSON for step details; capped so a pasted
    document never bloats the trajectory."""
    try:
        text = json.dumps(arguments, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(arguments)
    if len(text) > _MAX_DETAIL_ARGS_CHARS:
        return text[:_MAX_DETAIL_ARGS_CHARS] + "…[截断]"
    return text


def tool_detail(call: ToolCall, outcome: Any, ms: float) -> dict[str, Any]:
    """Structured facts for one tool step (single construction site for the
    parallel and serial execution paths so the two never drift)."""
    return {
        "tool_call_id": call.id,
        "args": capped_args(call.arguments),
        "ok": outcome.ok,
        "ms": ms,
        "title": outcome.title or call.name,
        **({"truncated": True} if outcome.metadata.get("truncated") else {}),
    }


async def run_mode(
    mode: Mode,
    *,
    llm: LLMClient,
    toolbelt: ToolRunner | None,
    messages: list[dict[str, Any]],
    limits: ModeLimits,
    on_step: StepCb = noop_step,
    on_delta: DeltaCb | None = None,
    on_event: EventCb = noop_event,
    continue_if_idle: bool = False,
    compress_budget: int = COMPRESS_BUDGET,
    governor: ContextGovernor | None = None,
    deadline: Deadline | None = None,
) -> str:
    """Uniform entry: each mode module registers its runner at import time
    (modes/registry.py), so this dispatcher never imports them and the
    mode -> base dependency stays one-way. The orchestrator persona forces
    ReAct. Streaming: when the llm offers complete_stream and the caller
    passes on_delta, REACT/DIRECT per-round completions stream with deltas
    batched through the coalescer; other modes' multi-way calls stay
    non-streaming (their intermediate products never face the user)."""
    runner = runner_for(mode)
    return await runner(
        llm=llm,
        toolbelt=toolbelt,
        messages=messages,
        limits=limits,
        on_step=on_step,
        on_delta=on_delta,
        on_event=on_event,
        continue_if_idle=continue_if_idle,
        compress_budget=compress_budget,
        governor=governor,
        deadline=deadline,
    )


__all__ = [
    "DeltaCb",
    "EventCb",
    "Mode",
    "ModeLimits",
    "StepCb",
    "capped_args",
    "noop_event",
    "noop_step",
    "run_mode",
    "sys_message",
    "tool_detail",
]
