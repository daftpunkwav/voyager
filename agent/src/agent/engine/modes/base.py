"""Mode vocabulary, callback contracts, shared step helpers and the run_mode
dispatcher.

The seven strategies live one per file (react / plan_execute / cot / tot /
got / reflexion / direct); each registers its runner in modes/registry.py at
import time, so this base never imports the mode modules (no cycle) and
run_mode dispatches through the registry. Rounds and tool calls are two
independent caps (ModeLimits); hitting either stops gracefully with an
explanation of how to raise it.

The composite modes (cot / tot / got / plan_execute / reflexion) run several
phases per invocation and delegate tool work to run_react slices. The shared
machinery they need - one invocation-level budget across phases, a counting
toolbelt view, step-list parsing, abort-prefix detection - lives here so the
per-mode files stay about strategy, not accounting.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from agent.context.compressor import COMPRESS_BUDGET
from agent.context.governor import ContextGovernor
from agent.contracts import ToolRunner
from agent.engine.modes.registry import runner_for
from agent.llm import LLMClient, ToolCall, Usage
from agent.runtime.deadline import Deadline


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
RawCb = Callable[[int, list, Any], Awaitable[None]]  # (round, request messages, LLMReply)
DeltaCb = Callable[[int, str], Awaitable[None]]  # (round, delta text)
#: Lifecycle event sink: (RuntimeEvent type, **payload). The instance binds
#: it to RuntimeEvents.emit with its run context; modes never see the bus.
EventCb = Callable[..., Awaitable[None]]


async def noop_step(kind: str, name: str, summary: str, detail: dict[str, Any]) -> None:
    return None


async def noop_event(type_: str, **payload: Any) -> None:
    return None


def sys_message(content: str) -> list[dict[str, Any]]:
    return [{"role": "system", "content": content}]


def capped_args(arguments: Any) -> str:
    """Tool arguments as compact JSON for step details, kept verbatim: the
    user asked for full fidelity (nothing truncated) in the trace details."""
    try:
        return json.dumps(arguments, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(arguments)


def round_text_detail(text: str) -> dict[str, Any]:
    """Full round output for the UI thinking block, verbatim."""
    if not text:
        return {}
    return {"text": text}


def reasoning_detail(reasoning: str) -> dict[str, Any]:
    """Model thinking for the UI thinking block, kept separate from the
    answer text, verbatim. Empty when the provider sent no separate
    reasoning channel."""
    if not reasoning:
        return {}
    return {"reasoning": reasoning}


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


# -- shared multi-phase mode machinery ----------------------------------------

#: Result prefixes run_react produces when a slice cannot finish its work;
#: composite modes treat any of them as a failed step/attempt, not an answer
ABORT_PREFIXES = ("[中断]", "[预算]", "[无工具可用]")

#: Rounds one composite-mode step slice may use (tool work inside a step
#: needs more than one round)
STEP_ROUNDS = 4

#: Upper bound on planned steps: a runaway step list is truncated, not
#: followed into an unbounded loop
MAX_PLAN_STEPS = 8

#: Tool room a slice falls back to when the invocation cap is unlimited
#: (react reads max_tool_calls as a hard cap, so 0 must never be handed down)
DEFAULT_TOOL_ROOM = 40

_STEP_LINE_RE = re.compile(r"^(?:\d{1,2}[、.):]|[-*•])\s*(\S.*)$")
_CJK_STEP_RE = re.compile(r"^[一二三四五六七八九十]{1,3}、\s*(\S.*)$")


def parse_steps(text: str) -> list[str]:
    """Numbered steps from a planning reply (arabic / CJK ordinals / dashes).

    A reply without any list shape degrades to one whole-text step: a plan
    phase can never silently produce zero work. Blank lines and a trailing
    "完成判定"-style prose block are dropped; each kept step is one line.
    """
    steps: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _STEP_LINE_RE.match(line) or _CJK_STEP_RE.match(line)
        if m:
            steps.append(m.group(1).strip())
    if not steps:
        whole = (text or "").strip()
        return [whole] if whole else []
    return steps


def looks_aborted(result: str) -> bool:
    """Whether a slice result is an abort/limit report rather than real work."""
    return any(result.startswith(prefix) for prefix in ABORT_PREFIXES)


class ModeBudget:
    """Cross-phase accounting for one mode invocation.

    Tokens (input+output), tool calls and rounds consumed so far, enforced
    against the invocation's ModeLimits: composite modes hand every phase and
    every run_react slice a budget slice, so hitting the invocation cap winds
    the whole strategy down, not just the current phase.
    """

    def __init__(self, limits: ModeLimits) -> None:
        self._limits = limits
        self.tokens_used = 0
        self.tool_calls_used = 0
        self.rounds_used = 0

    def add_usage(self, usage: Any) -> None:
        self.tokens_used += usage.input_tokens + usage.output_tokens

    def add_rounds(self, count: int) -> None:
        self.rounds_used += count

    def add_tool_calls(self, count: int) -> None:
        self.tool_calls_used += count

    def over_token_budget(self) -> bool:
        return 0 < self._limits.max_tokens <= self.tokens_used

    def rounds_exhausted(self) -> bool:
        """Whether the invocation's round cap is spent (react slices shrink
        toward one round before this trips; phases must gate on it so the
        invocation-level cap is honored, not just the per-slice caps)."""
        return 0 < self._limits.max_rounds <= self.rounds_used

    def slice(self, *, rounds: int, tools: int | None = None) -> ModeLimits:
        """A per-phase ModeLimits bounded by what the invocation has left.

        rounds is the phase's own preference (e.g. a small per-step cap);
        the effective value never exceeds the invocation remainder. Token
        caps are deliberately NOT propagated: a slice would read the
        invocation remainder as its own fresh cap and abort a single
        oversized-but-legitimate round; the invocation token budget is
        enforced by the mode between phases (over_token_budget) instead.
        """
        if self._limits.max_tool_calls > 0:
            tool_room = max(0, self._limits.max_tool_calls - self.tool_calls_used)
            if tools is not None:
                tool_room = min(tool_room, tools)
        else:
            # Unlimited invocation cap: a slice is bounded only by its own
            # preference (a literal 0 would read as a zero-call cap)
            tool_room = tools if tools is not None else DEFAULT_TOOL_ROOM
        round_room = min(rounds, max(1, self._limits.max_rounds - self.rounds_used))
        return ModeLimits(
            max_rounds=max(1, round_room),
            max_tool_calls=max(0, tool_room),
            max_tokens=0,
        )


class CountingToolbelt:
    """Delegating tool-surface view that counts executed calls, so a mode
    delegating to run_react slices keeps one invocation-level tool budget.
    Forwards the full surface run_react touches (specs / call / call_detailed
    / concurrent_safe / names)."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.calls = 0

    def specs(self) -> list[Any]:
        return self._inner.specs()

    def names(self) -> list[str]:
        return self._inner.names()

    def concurrent_safe(self, name: str) -> bool:
        return self._inner.concurrent_safe(name)

    async def call(self, call: ToolCall) -> str:
        return await self._inner.call(call)

    async def call_detailed(self, call: ToolCall, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        try:
            return await self._inner.call_detailed(call, *args, **kwargs)
        except TypeError:
            return await self._inner.call_detailed(call)


def counting_step(on_step: StepCb, budget: ModeBudget) -> StepCb:
    """Wrap a step sink so a ReAct slice's rounds and token usage land in the
    invocation budget: react reports one "llm" step named round-N per round,
    carrying its usage in the detail."""

    async def wrapped(kind: str, name: str, summary: str, detail: dict[str, Any]) -> None:
        if kind == "llm" and name.startswith("round-"):
            budget.add_rounds(1)
            budget.add_usage(
                Usage(
                    input_tokens=int((detail or {}).get("input_tokens") or 0),
                    output_tokens=int((detail or {}).get("output_tokens") or 0),
                )
            )
        await on_step(kind, name, summary, detail)

    return wrapped


def budget_reason(limits: ModeLimits, budget: ModeBudget) -> str:
    """Which invocation cap is spent (caller has verified at least one);
    names the limit so a wind-down report is actionable."""
    if budget.over_token_budget() and limits.max_tokens > 0:
        return f"token 上限({limits.max_tokens})"
    return f"轮数上限({limits.max_rounds})"


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
    on_raw: RawCb | None = None,
    continue_if_idle: bool = False,
    compress_budget: int = COMPRESS_BUDGET,
    governor: ContextGovernor | None = None,
    deadline: Deadline | None = None,
    conversational: bool = False,
) -> str:
    """Uniform entry: each mode module registers its runner at import time
    (modes/registry.py), so this dispatcher never imports them and the
    mode -> base dependency stays one-way. The orchestrator persona forces
    ReAct. Streaming: when the llm offers complete_stream and the caller
    passes on_delta, REACT/DIRECT per-round completions stream with deltas
    batched through the coalescer; other modes' multi-way calls stay
    non-streaming (their intermediate products never face the user)."""
    runner = runner_for(mode)
    kwargs: dict[str, Any] = {
        "llm": llm,
        "toolbelt": toolbelt,
        "messages": messages,
        "limits": limits,
        "on_step": on_step,
        "on_delta": on_delta,
        "on_event": on_event,
        "continue_if_idle": continue_if_idle,
        "compress_budget": compress_budget,
        "governor": governor,
        "deadline": deadline,
    }
    if mode is Mode.REACT:
        # The raw round log is a REACT-only surface: other modes' intermediate
        # products never face the user, so recording them buys nothing.
        kwargs["on_raw"] = on_raw
    if mode in (Mode.COT, Mode.PLAN_EXECUTE):
        # Only the modes with a closing synthesis phase shape their final
        # answer by it (chat reply vs task report); other runners have no
        # finalizer to tune.
        kwargs["conversational"] = conversational
    return await runner(**kwargs)


__all__ = [
    "ABORT_PREFIXES",
    "DEFAULT_TOOL_ROOM",
    "MAX_PLAN_STEPS",
    "STEP_ROUNDS",
    "CountingToolbelt",
    "DeltaCb",
    "EventCb",
    "Mode",
    "ModeBudget",
    "ModeLimits",
    "RawCb",
    "StepCb",
    "budget_reason",
    "capped_args",
    "counting_step",
    "looks_aborted",
    "noop_event",
    "noop_step",
    "parse_steps",
    "reasoning_detail",
    "round_text_detail",
    "run_mode",
    "sys_message",
    "tool_detail",
]
