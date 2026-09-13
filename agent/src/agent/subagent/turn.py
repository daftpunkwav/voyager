"""Turn execution for a SubagentInstance: run_turn and its step/delta/event
callbacks, moved here from instance.py (one file, one responsibility: the
per-turn machinery).

`inst` is duck-typed (SubagentInstance); importing the class here would cycle
through the tools package. The instance keeps thin delegating methods so the
public surface (instance.run_turn, scheduler callbacks) is unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from platform_contracts import DomainEvent, RuntimeEvent

from agent.context.editor import SUMMARY_MARK
from agent.runtime.current import current_instance
from agent.runtime.state import RunStatus
from agent.subagent.modes import Mode, ModeLimits, run_mode
from agent.tools.core.activate import graded_toolbelt, infer_domains, page_preactivate

if TYPE_CHECKING:
    from agent.subagent.instance import SubagentInstance

log = logging.getLogger("agent.runtime")


class PauseRequested(Exception):
    """Raised at a step boundary when the instance was flagged for a
    cooperative pause; run_turn turns it into the PAUSED state + event."""


async def run_turn(inst: SubagentInstance, user_text: str | None = None) -> str:
    """Run one turn (conversational = one Q/A round; task = run to completion)."""
    was_paused = inst.state.status is RunStatus.PAUSED
    inst.state.status = RunStatus.RUNNING
    if was_paused:
        await inst.events.emit(
            RuntimeEvent.AGENT_RESUMED, run_id=inst.state.run_id, subagent=inst.id
        )
    if inst.build_system is not None:
        # Rebuild the system prompt every turn so style/profile/page/digest
        # changes never go stale across turns; the turn's input rides along
        # as the memory read policy's recall query (resident relevance layer)
        inst.system_prompt = inst.build_system(inst.task, inst.persona, user_text or "")
    if inst.resume_messages:
        # Mid-turn resume: pending_messages already contains system /
        # history / this turn's tool entries, so skip history rebuild and
        # continue from the next complete after the crash point; the system
        # entry is recomputed so style/profile changes apply to the resume.
        # Resume carries no new input: the only entry point resume_run->start
        # passes no user_text.
        messages = [dict(m) for m in inst.resume_messages]
        inst.resume_messages = None
        if messages and messages[0].get("role") == "system":
            messages[0] = inst._system_message()
    else:
        if user_text:
            inst.history.append({"role": "user", "content": user_text})
        messages = [inst._system_message(), *inst.history]
    inst._turn_messages = messages  # live reference for mid-turn snapshots (on_step)
    belt = inst.toolbelt
    if inst.task.allowed_tools is None and inst.toolbelt.names():
        # Conversational instances (allowed_tools=None): the full tool table
        # is selectable, but each complete only receives activated schemas
        # (domain activation); the activation set lives on the instance and
        # persists across turns.
        if inst.active is None:
            inst.active = set()
        hinted = infer_domains(*(str(m.get("content") or "") for m in inst.history[-12:]))
        preactivate = list(hinted)
        if inst.pages is not None:
            cur = inst.pages.current()
            if cur is not None:
                domain = page_preactivate(cur.page)
                if domain and domain not in preactivate:
                    preactivate.append(domain)  # domain-page preactivation saves one activate round
        belt = graded_toolbelt(
            inst.toolbelt,
            inst.active,
            preactivate=tuple(preactivate),
        )
    # Prefix-cache diagnostics: fold this turn's request head; a changed
    # segment emits one debug line on the "agent.context.prefix" logger
    inst.prefix_watch.observe(
        system=str(messages[0].get("content") or "") if messages else "",
        tools=belt.names(),
    )
    await inst.events.emit(RuntimeEvent.RUN_STARTED, run_id=inst.state.run_id, subagent=inst.id)
    try:
        # Meta tools (context_status / compact_context) resolve the live
        # transcript through this ContextVar; set inside the try so the
        # finally always resets it, even when the turn is cancelled
        token = current_instance.set(inst)
        result = await run_mode(
            inst.task.mode or Mode.REACT,
            llm=inst.llm,
            toolbelt=belt,
            messages=messages,
            limits=inst.task.limits or ModeLimits(),
            on_step=inst._on_step,
            on_delta=inst._on_delta,
            on_event=inst._on_event,
            continue_if_idle=inst.task.conversational,
            compress_budget=inst.budget.compress_budget,
            governor=inst.governor(),
            deadline=inst.deadline,
        )
    except asyncio.CancelledError:
        # Hard cancellation (stop/shutdown): record the terminal state and
        # emit the event, then re-raise unchanged - swallowing cancellation
        # would leave the scheduler waiting forever. Event sending is best
        # effort: telemetry failure must not mask the cancellation itself.
        # When stopped via cancel_run the status is already CANCELLED; the
        # terminal state recorded here is not rolled back.
        if inst.state.status is RunStatus.RUNNING:
            inst.state.status = RunStatus.CANCELLED
        try:
            await inst.events.emit(
                RuntimeEvent.RUN_CANCELLED, run_id=inst.state.run_id, subagent=inst.id
            )
        except Exception:  # best effort: the event channel may be gone during shutdown
            log.debug(
                "failed to emit RunCancelled event (cancel semantics unaffected)", exc_info=True
            )
        raise
    except PauseRequested:
        # Cooperative pause (phase 20): stop at a paired boundary, persist a
        # mid-turn snapshot for resume_run, and announce it. The transcript
        # rolls back to the last paired exchange so a resume never continues
        # from a half-executed tool batch.
        inst.state.status = RunStatus.PAUSED
        try:
            await inst.events.emit(
                RuntimeEvent.AGENT_PAUSED, run_id=inst.state.run_id, subagent=inst.id
            )
            if inst.checkpoint_persist is not None:
                inst.state.resume = inst.build_resume_snapshot(
                    in_turn=True,
                    pending_messages=messages,
                ).to_dict()
                inst.checkpoint_persist(inst)
        except Exception:  # the pause itself must not fail the turn bookkeeping
            log.warning("pause bookkeeping failed for %s", inst.name, exc_info=True)
        finally:
            inst.pause_requested = False
        return "[已暂停] 已在当前步骤完成后暂停并保存检查点;用 resume_run 继续。"
    except Exception as exc:  # record failure and report; never break the scheduler
        inst.state.status = RunStatus.FAILED
        inst.state.error = f"{type(exc).__name__}: {exc}"
        await inst.events.emit(
            RuntimeEvent.RUN_FAILED, run_id=inst.state.run_id, error=inst.state.error
        )
        raise
    except BaseException as exc:  # catch-all terminal state: the instance never stays RUNNING
        inst.state.status = RunStatus.FAILED
        inst.state.error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        # The turn is over (success or failure): start()'s finally already
        # persisted the turn-boundary snapshot and no further step events
        # will fire; clear _turn_messages to stop mis-capturing
        inst._turn_messages = None
        current_instance.reset(token)
    if any(SUMMARY_MARK in str(m.get("content") or "") for m in messages):
        # Persist compaction across turns: the summary has replaced the
        # condensed middle, so write it back into history and later turns
        # will not re-summarize the same span; without the write-back every
        # turn would re-condense the same history.
        rebuilt: list[dict[str, Any]] = []
        for m in messages[
            1:
        ]:  # skip system; tool entries and empty tool-turn text stay out of history
            role = m.get("role")
            if role == "user":
                rebuilt.append({"role": "user", "content": str(m.get("content", ""))})
            elif role == "assistant":
                text = str(m.get("content", ""))
                if text:
                    rebuilt.append({"role": "assistant", "content": text})
        inst.history[:] = rebuilt
    inst.history.append({"role": "assistant", "content": result})
    inst._bound_history()
    inst.state.result = result
    if inst.task.conversational:
        inst.state.status = RunStatus.WAITING_INPUT
        if inst.reply_sink is not None:
            await inst.reply_sink(result)
    else:
        inst.state.status = RunStatus.COMPLETED
        await inst.events.emit(
            RuntimeEvent.AGENT_COMPLETED, run_id=inst.state.run_id, subagent=inst.id
        )
    return result


async def on_delta(inst: SubagentInstance, round_n: int, text: str) -> None:
    """Streaming delta events: conversational instances only.

    The single timeline carries only the main conversation's typing
    stream - background task instances run concurrently and multiple delta
    streams would interleave; their results still arrive via the completion
    message/card. When the LLM does not support streaming, run_mode falls
    back to complete, this callback is never invoked, and the event surface
    stays quiet naturally.
    """
    if not inst.task.conversational or not text:
        return
    await inst.events.emit(
        DomainEvent.AGENT_DELTA,
        run_id=inst.state.run_id,
        subagent=inst.name or inst.id,
        session=inst.session,
        round=round_n,
        text=text,
    )


async def on_event(inst: SubagentInstance, type_: str, **payload: Any) -> None:
    """Lifecycle events from the mode loop (LLM*/Tool*), stamped with this
    run's identity; the step trail stays the UI contract, these feed the
    trajectory projection and tracing."""
    await inst.events.emit(
        type_, run_id=inst.state.run_id, subagent=inst.name or inst.id, **payload
    )


async def on_step(
    inst: SubagentInstance, kind: str, name: str, summary: str, detail: dict[str, Any] | None = None
) -> None:
    inst.state.add_step(kind, name, summary, detail)
    # ReAct round / tool-call counters (kept in sync): a "llm" step named
    # round-N is one complete round, a tool step is one call; resumed runs
    # continue counting from the persisted values
    if kind == "llm" and name.startswith("round-"):
        inst.state.rounds += 1
        # Provider-reported input usage anchors the context status: the
        # estimate alone lags the real prefix size the provider saw
        detail = detail or {}
        input_tokens = int(detail.get("input_tokens") or 0)
        inst.usage.record(input_tokens)
        # Prefix-cache health: every round reports what went out and what the
        # provider cached; the watch turns cold-after-warm rounds into break
        # signals (see agent.context.prefix_watch)
        inst.prefix_watch.observe_round(
            input_tokens=input_tokens,
            cached_tokens=int(detail.get("cached_tokens") or 0),
            messages=inst._turn_messages or [],
        )
    elif kind == "tool":
        inst.state.tool_calls += 1
    # Steps go into the event stream (gateway _STREAM_TYPES agent.step) so
    # Chat can see which tool is being called; not part of history rebuild,
    # just live progress.
    await inst.events.emit(
        DomainEvent.AGENT_STEP,
        run_id=inst.state.run_id,
        subagent=inst.name or inst.id,
        session=inst.session,
        name=name,
        kind=kind,
        summary=(summary or "")[:120],
        detail=detail or {},
    )
    # Refresh the DigestStore so the master's global layer render stays current.
    if inst.sync_digest is not None:
        inst.sync_digest(inst)
    mid_save_checkpoint(inst)
    if inst.pause_requested:
        raise PauseRequested()


def mid_save_checkpoint(inst: SubagentInstance) -> None:
    """Incremental mid-ReAct persistence: refresh the on-disk snapshot each
    step so a crash can resume from mid-run.

    Only for task-mode REACT (conversational / other modes still persist at
    turn end); persist is injected by the spawner (= checkpoints.save) and
    no-op when absent. Writes a single JSON file synchronously each step:
    correctness first, no debouncing.
    """
    if (
        inst.checkpoint_persist is None
        or inst._turn_messages is None
        or inst.task.conversational
        or (inst.task.mode or Mode.REACT) is not Mode.REACT
    ):
        return
    inst.state.resume = inst.build_resume_snapshot(
        in_turn=True,
        pending_messages=inst._turn_messages,
    ).to_dict()
    inst.checkpoint_persist(inst)


__all__ = ["PauseRequested", "mid_save_checkpoint", "on_delta", "on_event", "on_step", "run_turn"]
