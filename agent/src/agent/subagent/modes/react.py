"""REACT: the reasoning-acting loop and the only agent-loop implementation.

When tool_calls come back, keep calling complete itself until the model
produces a Final Answer. Plain text with no Action yet this turn is not
treated as an ending (small talk excepted) - this is the loop's exit
condition, not a scan for polite acknowledgments. specs are re-fetched
before each complete (domain activation). Context management is LLM-driven:
each round the governor checks usage against the auto-compact threshold and,
past it, the editor restructures the transcript; without a governor a purely
mechanical truncation of old tool text runs instead. Assistant(tool_calls)/
tool pairs are never split on any path. Tool calls pass loop detection: the
same signature repeating to a threshold within the sliding window trips an
early circuit break instead of burning the budget to max_rounds.

Lifecycle events (RuntimeEvent) are raised through on_event around every
completion and tool call; the step trail (on_step) stays the UI contract.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from agent.context.compressor import COMPRESS_BUDGET, compress
from agent.context.governor import ContextGovernor
from agent.contracts import ToolRunner
from agent.llm import LLMClient, TextPart, ToolCall, content_to_text
from agent.prompts import P, render
from agent.runtime.deadline import Deadline
from agent.runtime.events import RuntimeEvent
from agent.runtime.loop_advisory import LoopAdvisory
from agent.runtime.loop_detection import LoopDetector
from agent.runtime.trace import start_span
from agent.subagent.modes.base import (
    STEP_ROUNDS,
    CountingToolbelt,
    DeltaCb,
    EventCb,
    Mode,
    ModeBudget,
    ModeLimits,
    RawCb,
    StepCb,
    counting_step,
    noop_event,
    reasoning_detail,
    round_text_detail,
    tool_detail,
)
from agent.subagent.modes.registry import register_mode
from agent.subagent.modes.streaming import complete_streaming, delta_timer, run_phase

# ReAct continuation: text with zero tool_calls is not a valid ending
# (small talk excepted). This does not scan for polite acknowledgments -
# those are model endings, not loop conditions.
CONTINUE_MARK = "[react]"
CHITCHAT_RE = re.compile(
    r"^(你好|嗨|哈喽|在吗|早上好|晚上好|谢谢|感谢|嗯+|ok|okay|好)$",
    re.IGNORECASE,
)


def _emergency_truncate(messages: list[dict[str, Any]], budget: int) -> None:
    """Overflow-recovery last resort: cap every non-system message's content so
    even a single huge entry (a giant pasted input, an unspillable tool row)
    cannot keep the transcript over budget. In-place; truncation is marked so
    the model knows text is missing. Multi-modal list content is preserved
    structurally (only text parts are capped)."""
    cap = max(200, budget // 4)
    for i, m in enumerate(messages):
        if i == 0 and m.get("role") == "system":
            continue
        content = m.get("content")
        if isinstance(content, list):
            truncated: list[Any] = []
            changed = False
            for part in content:
                if isinstance(part, TextPart) and len(part.text) > cap:
                    truncated.append(TextPart(text=part.text[:cap] + " …[上下文溢出截断]"))
                    changed = True
                elif isinstance(part, dict) and isinstance(part.get("text"), str):
                    text = part["text"]
                    if len(text) > cap:
                        truncated.append({**part, "text": text[:cap] + " …[上下文溢出截断]"})
                        changed = True
                    else:
                        truncated.append(part)
                else:
                    truncated.append(part)
            if changed:
                messages[i] = {**m, "content": truncated}
            continue
        text = content_to_text(content)
        if len(text) > cap:
            messages[i] = {
                **m,
                "content": text[:cap] + " …[上下文溢出截断]",
            }


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") != "user":
            continue
        content = content_to_text(m.get("content"))
        if CONTINUE_MARK in content:
            continue
        return content.strip()
    return ""


def _should_continue_react(messages: list[dict[str, Any]], tool_calls_used: int) -> bool:
    """Plain-text ending with no Action yet this turn -> continue the same
    ReAct loop.

    Does not read assistant wording (no polite-phrase matching). Small talk is
    allowed to end with zero tools; once one continuation already happened, a
    second plain text is respected (the model explicitly said no tools are
    needed).
    """
    if tool_calls_used > 0:
        return False
    if any(CONTINUE_MARK in content_to_text(m.get("content")) for m in messages):
        return False
    user = _last_user_text(messages)
    return not (not user or CHITCHAT_RE.match(user))


def _tool_event(outcome: Any) -> str:
    return RuntimeEvent.TOOL_COMPLETED if outcome.ok else RuntimeEvent.TOOL_FAILED


def _context_step(report: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Step-trail entry for one governor.enforce/compact report: a prune
    (cleared old tool results) gets its own wording — it is not an LLM
    compaction. Returns (summary, detail)."""
    mode = report.get("mode", "mechanical")
    if mode == "prune":
        summary = f"旧工具结果已清理(回收约 {report.get('recovered_tokens', 0)} tokens)"
        op = "prune"
    else:
        summary = f"上下文已自动压缩({mode})"
        op = "compact"
    return summary, {"op": op, "mode": mode}


async def _run_tool(
    toolbelt: ToolRunner, call: ToolCall, on_event: EventCb, deadline: Deadline | None = None
) -> tuple[Any, float]:
    """One tool call bracketed by ToolStarted / ToolCompleted|ToolFailed; a
    harness deadline backstops calls that declare no per-tool timeout."""
    await on_event(RuntimeEvent.TOOL_STARTED, tool=call.name, tool_call_id=call.id)
    start = time.perf_counter()

    async def _on_progress(progress: float, message: str = "") -> None:
        await on_event(
            RuntimeEvent.TOOL_PROGRESS,
            tool=call.name,
            tool_call_id=call.id,
            progress=progress,
            message=message,
        )

    async def _call() -> Any:
        try:
            return await toolbelt.call_detailed(call, on_progress=_on_progress)
        except TypeError:
            return await toolbelt.call_detailed(call)

    if deadline is not None:
        outcome = await deadline.run_tool(_call, tool=call.name)
    else:
        outcome = await _call()
    ms = round((time.perf_counter() - start) * 1000, 1)
    await on_event(_tool_event(outcome), tool=call.name, tool_call_id=call.id, ms=ms)
    return outcome, ms


async def run_react(
    llm: LLMClient,
    toolbelt: ToolRunner | None,
    messages: list[dict[str, Any]],
    limits: ModeLimits,
    on_step: StepCb,
    *,
    on_delta: DeltaCb | None = None,
    on_event: EventCb = noop_event,
    on_raw: RawCb | None = None,
    continue_if_idle: bool = False,
    compress_budget: int = COMPRESS_BUDGET,
    governor: ContextGovernor | None = None,
    deadline: Deadline | None = None,
) -> str:
    tool_calls_used = 0
    tokens_used = 0
    loops = LoopDetector()
    advisory = LoopAdvisory()  # one reminder round per invocation, then abort
    # Answer produced before the idle-continue nudge: the nudge round is loop
    # plumbing, and the "no tool needed" justification the model writes under it
    # must never replace the real answer the user already saw streaming
    pending_answer: str | None = None
    # Context-overflow recovery: one aggressive compact + retry; a second
    # overflow means even the compressed transcript cannot fit and the turn
    # ends with an actionable message instead of a raw provider error
    overflow_retried = False
    for round_n in range(1, limits.max_rounds + 1):
        specs = toolbelt.specs() if toolbelt is not None else None
        if governor is not None:
            report = await governor.enforce(messages)
            if report is not None:
                summary, detail = _context_step(report)
                await on_step("system", "compact", summary, detail)
        else:
            messages[:] = compress(messages, budget=compress_budget, prune=False)
        # Round timing: wall latency always; TTFT only when the caller
        # consumes deltas (streaming active) - otherwise there is no first
        # token to time. The wrapper preserves the tiering: on_delta=None
        # still means a plain complete() call.
        round_start = time.perf_counter()
        round_delta = None
        first_delta_at: list[float] = []
        if on_delta is not None:
            round_delta, first_delta_at = delta_timer(on_delta, on_event=on_event, round_n=round_n)
        await on_event(RuntimeEvent.LLM_STARTED, round=round_n, streaming=on_delta is not None)
        round_span = start_span(
            f"llm:round-{round_n}",
            kind="CLIENT",
            round_n=round_n,
            model=getattr(llm, "model", ""),
        )
        with round_span:
            if deadline is not None:
                # default-arg binding: the loop variables must be frozen now,
                # not whenever wait_for first calls the factory
                reply = await deadline.run_round(
                    lambda s=specs, r=round_delta, n=round_n: complete_streaming(
                        llm, messages, s, r, round_n=n, on_event=on_event
                    )
                )
            else:
                reply = await complete_streaming(
                    llm, messages, specs, round_delta, round_n=round_n, on_event=on_event
                )
            round_span.set_attributes(
                model=reply.model or getattr(llm, "model", ""),
                **{
                    "gen_ai.request.model": reply.model or getattr(llm, "model", ""),
                    "gen_ai.usage.input_tokens": reply.usage.input_tokens,
                    "gen_ai.usage.output_tokens": reply.usage.output_tokens,
                    "gen_ai.usage.cached_tokens": reply.usage.cached_tokens,
                },
            )
        round_ms = (time.perf_counter() - round_start) * 1000
        tokens_used += reply.usage.input_tokens + reply.usage.output_tokens
        if limits.max_tokens > 0 and tokens_used >= limits.max_tokens:
            partial = (
                render(P.modes.react.partial_result, text=reply.text)
                if reply.text
                else P.modes.react.no_final_text
            )
            return render(P.modes.react.token_budget, max_tokens=limits.max_tokens, partial=partial)
        await on_event(
            RuntimeEvent.LLM_COMPLETED,
            round=round_n,
            ms=round(round_ms, 1),
            input_tokens=reply.usage.input_tokens,
            output_tokens=reply.usage.output_tokens,
            degraded=bool(reply.degraded),
            overflow=bool(reply.overflow),
        )
        if reply.overflow:
            if overflow_retried:
                return P.modes.react.overflow
            overflow_retried = True
            if governor is not None:
                # Aggressive recovery: aim for the mechanical fallback budget,
                # the smallest sane target, before the per-message truncate
                report = await governor.compact(
                    messages, target=min(governor.target_tokens(), compress_budget)
                )
                if report is not None:
                    await on_step(
                        "system",
                        "compact",
                        f"上下文溢出,已强制压缩({report.get('mode', 'mechanical')})",
                        {"op": "compact", "mode": report.get("mode", "mechanical")},
                    )
            else:
                messages[:] = compress(messages, budget=compress_budget, prune=False)
            _emergency_truncate(messages, compress_budget)
            continue
        await on_step(
            "llm",
            f"round-{round_n}",
            (reply.text or f"{len(reply.tool_calls)} 个工具调用")[:120],
            {
                "round": round_n,
                "tool_calls": [c.name for c in reply.tool_calls],
                "ms": round(round_ms, 1),
                **(
                    {"ttft_ms": round((first_delta_at[0] - round_start) * 1000, 1)}
                    if first_delta_at
                    else {}
                ),
                "input_tokens": reply.usage.input_tokens,
                "output_tokens": reply.usage.output_tokens,
                "cached_tokens": reply.usage.cached_tokens,
                # Degraded rounds (quota / provider-failure placeholders) are
                # real steps, but the turn close-out must not present their
                # text as a normal answer (see turn._turn_degraded).
                "degraded": bool(reply.degraded),
                # Truncation visibility: finish_reason=length/max_tokens means
                # the answer was cut off by the output cap — the UI flags the
                # round instead of presenting it as complete.
                **({"truncated": True} if reply.truncated else {}),
                # Provider response metadata (finish_reason / request id /
                # service tier) for the step fact sheet; empty keys dropped.
                **({"meta": {k: v for k, v in reply.meta.items() if v}} if reply.meta else {}),
                # Full round output so the chat UI can show the complete
                # thinking text, not just the 120-char summary prefix
                **round_text_detail(reply.text or ""),
                # Model thinking on its own channel (never mixed into text);
                # empty when the provider sent no separate reasoning stream
                **reasoning_detail(reply.reasoning or ""),
                # The adapter-resolved model: model switches become visible
                # in the trajectory round by round
                **({"model": reply.model} if getattr(reply, "model", "") else {}),
            },
        )
        if on_raw is not None:
            # Raw round log: the exact request transcript plus the response,
            # stored outside the display projection (capped by the store).
            await on_raw(round_n, messages, reply)
        if reply.final:
            text = reply.text or ""
            # Output-cap truncation (provider finish_reason): the answer the
            # user is about to read is incomplete — say so instead of letting
            # it pass as a normal ending. The marker scopes to the return
            # value: this round's messages keep the model's own text (no
            # in-round imitation), while turn.py persists the marked text into
            # inst.history — deliberately, so the NEXT turn also knows the
            # previous answer was cut and can offer to continue instead of
            # treating it as complete (the web UI renders its own badge via
            # the step's truncated flag).
            truncated_reply = reply.truncated and text
            user_text = f"{text}\n\n{P.modes.react.truncation}" if truncated_reply else text
            # With tool_calls this branch is unreachable - the loop is still
            # calling the API itself. Plain text = the model declared Final
            # Answer. A non-chitchat round with no Action yet does not count as
            # an ending: write the text back as a Thought and complete again.
            if (
                continue_if_idle
                and round_n < limits.max_rounds
                and _should_continue_react(messages, tool_calls_used)
            ):
                if text:
                    pending_answer = text
                messages.append({"role": "assistant", "content": text})
                messages.append(
                    {
                        "role": "user",
                        "content": render(P.modes.react.continue_idle, mark=CONTINUE_MARK),
                    }
                )
                continue
            if pending_answer is not None and tool_calls_used == 0:
                # The continuation only confirmed "no tools needed": deliver the
                # pre-nudge answer, not the forced justification
                return pending_answer
            return user_text
        if toolbelt is None:
            return reply.text or "[无工具可用] LLM 请求了工具但未授予"
        # Tool-cap truncation: unexecuted calls stay out of assistant.tool_calls
        # so "call without result" never triggers an endpoint 400
        truncated = False
        pending = list(reply.tool_calls)
        if tool_calls_used + len(pending) > limits.max_tool_calls:
            pending = pending[: limits.max_tool_calls - tool_calls_used]
            truncated = True
        if not pending:
            return render(P.modes.react.tool_cap, max_tool_calls=limits.max_tool_calls)
        # Loop detection runs over the batch before anything executes: the
        # calls up to (not including) the tripping one are the executable
        # prefix; the assistant entry below carries only those, so the
        # "every call has a result" pairing holds even on a mid-batch trip.
        executable: list[ToolCall] = []
        tripped: ToolCall | None = None
        for call in pending:
            if loops.record(call.name, call.arguments):
                tripped = call
                break
            executable.append(call)
        if tripped is not None and not executable:
            return render(
                P.modes.loop_abort,
                tool=tripped.name,
                window=loops.window,
                threshold=loops.threshold,
            )
        # Neutral back-fill: one assistant entry carrying this round's tool_calls
        # (with ids), then one result entry per call carrying the same
        # tool_call_id; wire formats per provider (OpenAI tool_call_id /
        # Anthropic tool_use_id) are translated by the packages/llm client.
        # Stored thinking blocks ride along for verbatim echo-back while tool
        # use continues (extended thinking); attached only when present so
        # chat-format payloads never gain unknown message fields.
        assistant_entry: dict[str, Any] = {
            "role": "assistant",
            "content": reply.text or "",
            "tool_calls": [
                {"id": call.id, "name": call.name, "arguments": call.arguments}
                for call in executable
            ],
        }
        if reply.thinking_blocks:
            assistant_entry["thinking_blocks"] = [dict(b) for b in reply.thinking_blocks]
        messages.append(assistant_entry)
        tool_calls_used += len(executable)
        # Consecutive-safe partitioning (claude-code style): runs of
        # concurrent-safe calls execute in parallel, a write/unsafe call forms
        # a singleton serial batch — mixed rounds no longer serialize wholly.
        # Results back-fill in call order either way, so the transcript stays
        # deterministic.
        batches: list[list[ToolCall]] = []
        for call in executable:
            safe = toolbelt.concurrent_safe(call.name)
            joins_prev = safe and bool(batches) and toolbelt.concurrent_safe(batches[-1][-1].name)
            if joins_prev:
                batches[-1].append(call)
            else:
                batches.append([call])
        for batch in batches:
            if len(batch) > 1:
                batch_start = time.perf_counter()
                outcomes = await asyncio.gather(
                    *(_run_tool(toolbelt, c, on_event, deadline) for c in batch)
                )
                batch_ms = round((time.perf_counter() - batch_start) * 1000, 1)
                pairs = [(call, outcome, batch_ms) for call, (outcome, _ms) in zip(batch, outcomes)]
            else:
                call = batch[0]
                outcome, call_ms = await _run_tool(toolbelt, call, on_event, deadline)
                pairs = [(call, outcome, call_ms)]
            for call, outcome, ms in pairs:
                # The tool entry is appended before reporting: the mid-turn snapshot
                # is captured inside on_step from messages and must see the just
                # landed result; in multi-call rounds the tail at on_step time may
                # still be a partial group - the snapshot side's _paired_messages
                # rolls back to a paired boundary as a backstop.
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": outcome.text,
                    }
                )
                await on_step("tool", call.name, outcome.text[:120], tool_detail(call, outcome, ms))
        if tripped is not None or truncated:
            if tripped is not None:
                reminder = advisory.on_trip(
                    tool=tripped.name, threshold=loops.threshold, window=loops.window
                )
                if reminder is not None:
                    # Two-level guard: the first trip is a nudge, not an abort;
                    # the next identical trip ends the turn in this same branch
                    messages.append({"role": "user", "content": reminder})
                    await on_step("llm", "loop-advisory", reminder[:120], {"advisory": True})
                    continue
                return render(
                    P.modes.loop_abort,
                    tool=tripped.name,
                    window=loops.window,
                    threshold=loops.threshold,
                )
            return render(P.modes.react.tool_cap, max_tool_calls=limits.max_tool_calls)
    return render(P.modes.react.rounds_cap, max_rounds=limits.max_rounds)


async def run_step(
    *,
    llm: LLMClient,
    toolbelt: ToolRunner | None,
    messages: list[dict[str, Any]],
    on_step: StepCb,
    on_event: EventCb,
    continue_if_idle: bool,
    compress_budget: int,
    governor: ContextGovernor | None,
    deadline: Deadline | None,
    budget: ModeBudget,
    belt: CountingToolbelt | None,
    rounds: int | None = None,
) -> str:
    """One composite-mode step on the shared transcript: a bounded ReAct
    slice when tools are granted (the slice's rounds/tool calls/token usage
    fold into the invocation budget via the counting wrappers), a plain
    completion otherwise. `rounds` overrides the default per-step cap.
    Returns the step result text; abort reports flow through unchanged so
    the caller can tell a failed step from real work."""
    if governor is not None:
        report = await governor.enforce(messages)
        if report is not None:
            summary, detail = _context_step(report)
            await on_step("system", "compact", summary, detail)
    if toolbelt is not None and belt is not None:
        before_calls = belt.calls
        result = await run_react(
            llm,
            belt,
            messages,
            budget.slice(rounds=rounds if rounds is not None else STEP_ROUNDS),
            counting_step(on_step, budget),
            on_event=on_event,
            continue_if_idle=continue_if_idle,
            compress_budget=compress_budget,
            governor=governor,
            deadline=deadline,
        )
        budget.add_tool_calls(belt.calls - before_calls)
        return result
    reply = await run_phase(
        llm=llm,
        messages=messages,
        on_event=on_event,
        deadline=deadline,
        budget=budget,
    )
    return reply.text or ""


__all__ = ["CHITCHAT_RE", "CONTINUE_MARK", "run_react", "run_step"]


register_mode(Mode.REACT, run_react)
