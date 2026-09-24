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
import re
from typing import TYPE_CHECKING, Any

from platform_capability import current_chat_session
from platform_contracts import DomainEvent, RuntimeEvent

from agent.context.editor import SUMMARY_MARK
from agent.personas import PERSONAS, Persona, resolve_persona
from agent.runtime.current import current_instance
from agent.runtime.state import RunStatus
from agent.runtime.trace import start_span
from agent.subagent.modes import Mode, ModeLimits, run_mode
from agent.tools.core.activate import graded_toolbelt, infer_domains, page_preactivate

if TYPE_CHECKING:
    from agent.subagent.instance import SubagentInstance

log = logging.getLogger("agent.runtime")


def _member_view(member: str) -> Persona | None:
    """Resolve an @-mention / handoff target into a team-member persona.

    Empty (the resident host speaks), "orchestrator", and unknown keys all
    return None — those ride the ordinary host view. A known teammate returns
    its Persona: the member turn speaks under that identity, with the
    persona's own system layers, tool surface, and default mode.
    """
    key = member.strip()
    if not key or key == "orchestrator":
        return None
    preset = resolve_persona(key)
    if preset is None or preset.key == "orchestrator":
        return None
    return preset


def _speaker_label(inst: SubagentInstance) -> str:
    """Event attribution: the speaking member's display name during a member
    turn, else the instance name (session instances are named "chat")."""
    return inst._member_label or inst.name or inst.id


def _transcript_view(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shared group-chat transcript -> LLM message list.

    Assistant entries carrying a speaker (a teammate's turn) render their
    display name into the text as a 【name】 prefix, so every model sees who
    said what; entries without one are the host's own words and stay bare.
    Consecutive assistant messages merge into one entry: several providers
    reject or misbehave on adjacent assistant turns, and a merged block is
    exactly how a chat transcript reads anyway.
    """
    out: list[dict[str, Any]] = []
    for m in history:
        role = m.get("role")
        text = str(m.get("content") or "")
        if role == "assistant":
            speaker = str(m.get("speaker") or "")
            if speaker:
                preset = resolve_persona(speaker)
                name = preset.display_name if preset is not None else speaker
                text = f"【{name}】{text}"
            prev = out[-1] if out else None
            if prev is not None and prev.get("role") == "assistant":
                prev["content"] = f"{prev['content']}\n\n{text}"
                continue
        out.append({"role": role, "content": text})
    return out


class PauseRequested(Exception):
    """Raised at a step boundary when the instance was flagged for a
    cooperative pause; run_turn turns it into the PAUSED state + event."""


def _turn_degraded(inst: SubagentInstance) -> bool:
    """Whether this turn's latest LLM round was harness degradation text
    (quota / provider failure) rather than model output. Read back from the
    round step trail instead of sniffing reply-text prefixes."""
    for step in reversed(inst.state.steps):
        if step.kind == "llm":
            return bool((step.detail or {}).get("degraded"))
    return False


async def run_turn(
    inst: SubagentInstance, user_text: str | None = None, *, member: str = ""
) -> str:
    """Run one turn (conversational = one Q/A round; task = run to completion).

    `member` names a resident teammate answering an @-mention or handoff: the
    turn speaks under that persona (its own system layers, tool surface and
    default mode) over the shared session transcript, and its reply lands in
    the group timeline attributed to it. Empty = the resident host (Lucien).
    """
    view = _member_view(member)
    was_paused = inst.state.status is RunStatus.PAUSED
    inst.state.status = RunStatus.RUNNING
    if view is not None:
        inst._member_label = view.display_name
        inst._member_persona = view.key
    try:
        return await _run_turn(inst, user_text, view, was_paused)
    finally:
        inst._member_label = ""
        inst._member_persona = ""


async def _run_turn(
    inst: SubagentInstance, user_text: str | None, view: Persona | None, was_paused: bool
) -> str:
    if was_paused:
        await inst.events.emit(
            RuntimeEvent.AGENT_RESUMED, run_id=inst.state.run_id, subagent=_speaker_label(inst)
        )
    member_prompt = ""
    if view is not None and inst.build_system is not None:
        # The member's own persona layers over the shared session context;
        # rebuilt every turn like the host prompt so style/profile changes
        # never go stale
        member_prompt = inst.build_system(inst.task, view.key, user_text or "")
    elif inst.build_system is not None:
        # Rebuild the system prompt every turn so style/profile/page/digest
        # changes never go stale across turns; the turn's input rides along
        # as the memory read policy's recall query (resident relevance layer)
        inst.system_prompt = inst.build_system(inst.task, inst.persona, user_text or "")
    if inst.resume_messages and view is None:
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
        messages = [
            inst._system_message(member_prompt),
            *_transcript_view(inst.history),
        ]
    inst._turn_messages = messages  # live reference for mid-turn snapshots (on_step)
    belt = inst.toolbelt
    if view is not None and view.tool_allow is not None:
        # Member turn: the teammate works on its own curated surface (trimmed
        # view, never written back — the resident host keeps its full table)
        belt = inst.toolbelt.trimmed(view.tool_allow)
    elif view is None and inst.task.allowed_tools is None and inst.toolbelt.names():
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
    await inst.events.emit(
        RuntimeEvent.RUN_STARTED, run_id=inst.state.run_id, subagent=_speaker_label(inst)
    )
    turn_span = start_span(
        "agent:turn",
        subagent=_speaker_label(inst),
        session=inst.session,
        run_id=inst.state.run_id,
        conversational=inst.task.conversational,
    )
    with turn_span:
        try:
            # Meta tools (context_status / compact_context) resolve the live
            # transcript through this ContextVar; set inside the try so the
            # finally always resets it, even when the turn is cancelled
            token = current_instance.set(inst)
            # Domain capabilities called during this turn (create_note etc.)
            # read this to stamp their events with the session, so history
            # pages and SSE routing attribute them to the right chat lane
            session_token = current_chat_session.set(inst.session)
            try:
                member_mode = Mode(view.default_mode) if view is not None else None
            except ValueError:  # broken mode in a persona file: ride react
                member_mode = None
            result = await run_mode(
                member_mode or inst.task.mode or Mode.REACT,
                llm=inst.llm,
                toolbelt=belt,
                messages=messages,
                limits=inst.task.limits or ModeLimits(),
                on_step=inst._on_step,
                on_delta=inst._on_delta,
                on_event=inst._on_event,
                on_raw=inst._on_raw,
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
                    RuntimeEvent.RUN_CANCELLED,
                    run_id=inst.state.run_id,
                    subagent=_speaker_label(inst),
                )
            except Exception:  # best effort: the event channel may be gone during shutdown
                log.debug(
                    "failed to emit RunCancelled event (cancel semantics unaffected)", exc_info=True
                )
            # Conversational closure: without a closing chat message the UI waits
            # in the running state forever (the reply sink is success-only).
            if inst.task.conversational and inst.reply_sink is not None:
                try:
                    # kind=notice: not a conversation turn (never enters the
                    # session history), so fork's keep_messages counting and
                    # the UI's notice styling both stay correct.
                    await inst.reply_sink(
                        "[已中断] 本回合被中断;可重新发送或换个说法继续。",
                        "notice",
                        speaker=view.key if view is not None else "",
                    )
                except Exception:  # best effort, same as the event above
                    log.debug("failed to emit cancel closure message", exc_info=True)
            raise
        except PauseRequested:
            # Cooperative pause (phase 20): stop at a paired boundary, persist a
            # mid-turn snapshot for resume_run, and announce it. The transcript
            # rolls back to the last paired exchange so a resume never continues
            # from a half-executed tool batch.
            inst.state.status = RunStatus.PAUSED
            try:
                await inst.events.emit(
                    RuntimeEvent.AGENT_PAUSED,
                    run_id=inst.state.run_id,
                    subagent=_speaker_label(inst),
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
            try:
                await inst.events.emit(
                    RuntimeEvent.RUN_FAILED, run_id=inst.state.run_id, error=inst.state.error
                )
            except Exception:  # best effort: telemetry must not mask the real failure
                log.debug("failed to emit RunFailed event", exc_info=True)
            # Conversational closure: a failed turn must still end the chat
            # exchange, otherwise the UI stays in the running state forever.
            if inst.task.conversational and inst.reply_sink is not None:
                try:
                    await inst.reply_sink(
                        f"[回合失败] {inst.state.error}",
                        "error",
                        speaker=view.key if view is not None else "",
                    )
                except Exception:  # best effort: closure must not mask the failure
                    log.debug("failed to emit failure closure message", exc_info=True)
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
            current_chat_session.reset(session_token)
            # Fold this turn's round count into the raw-log numbering base so
            # the next turn's raw rounds continue past it instead of colliding
            inst._fold_raw_round_base()
        if any(SUMMARY_MARK in str(m.get("content") or "") for m in messages):
            # Persist compaction across turns: the summary has replaced the
            # condensed middle, so write it back into history and later turns
            # will not re-summarize the same span; without the write-back every
            # turn would re-condense the same history.
            rebuilt: list[dict[str, Any]] = []
            # _transcript_view folds a teammate's speaker into a leading
            # 【display name】 prefix and keeps the wire view key-clean, so
            # the key never survives onto these messages: recover it here
            # (display name -> persona key) and strip the prefix again, so
            # history keeps its invariant "raw text + optional speaker" and
            # the next turn's view prefixes exactly once.
            by_display = {p.display_name: k for k, p in PERSONAS.items()}
            for m in messages[
                1:
            ]:  # skip system; tool entries and empty tool-turn text stay out of history
                role = m.get("role")
                if role == "user":
                    rebuilt.append({"role": "user", "content": str(m.get("content", ""))})
                elif role == "assistant":
                    text = str(m.get("content", ""))
                    if text:
                        entry = {"role": "assistant", "content": text}
                        speaker = str(m.get("speaker") or "")
                        if not speaker:
                            prefixed = re.match(r"^【([^】]+)】", text)
                            if prefixed is not None:
                                key = by_display.get(prefixed.group(1))
                                if key is not None:
                                    speaker = key
                                    entry["content"] = text[prefixed.end() :].lstrip()
                        if speaker:
                            entry["speaker"] = speaker
                        rebuilt.append(entry)
            inst.history[:] = rebuilt
        closing: dict[str, Any] = {"role": "assistant", "content": result}
        if view is not None:
            # The group transcript attributes this turn's words to the member
            closing["speaker"] = view.key
        inst.history.append(closing)
        inst._bound_history()
        inst.state.result = result
        if inst.task.conversational:
            inst.state.status = RunStatus.WAITING_INPUT
            if inst.reply_sink is not None:
                # Degraded LLM text (quota / provider failure placeholders) must
                # not masquerade as a normal answer: the latest llm step carries
                # the degraded flag, so read it back instead of sniffing prefixes.
                try:
                    await inst.reply_sink(
                        result,
                        "error" if _turn_degraded(inst) else "message",
                        speaker=view.key if view is not None else "",
                    )
                except Exception:  # best effort: the turn result is already in
                    # history/state; a broken reply channel must not turn the
                    # finished turn into a failure (master's persist would be skipped)
                    log.warning("failed to deliver the turn reply for %s", inst.name, exc_info=True)
        elif _turn_degraded(inst):
            # A task turn that ended on degraded harness text (provider
            # 4xx/quota placeholder instead of a model answer — earlier rounds
            # may still have run tools): mark it failed instead of dressing the
            # failure up as a completed result — wait_subagent callers must see
            # the failure.
            inst.state.status = RunStatus.FAILED
            inst.state.error = result
            try:
                await inst.events.emit(
                    RuntimeEvent.RUN_FAILED, run_id=inst.state.run_id, error=result
                )
            except Exception:  # best effort: the failure is already on the state
                log.debug("failed to emit degraded RunFailed event", exc_info=True)
        else:
            inst.state.status = RunStatus.COMPLETED
            await inst.events.emit(
                RuntimeEvent.AGENT_COMPLETED,
                run_id=inst.state.run_id,
                subagent=_speaker_label(inst),
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
        subagent=_speaker_label(inst),
        session=inst.session,
        round=round_n,
        text=text,
    )


async def on_event(inst: SubagentInstance, type_: str, **payload: Any) -> None:
    """Lifecycle events from the mode loop (LLM*/Tool*), stamped with this
    run's identity; the step trail stays the UI contract, these feed the
    trajectory projection and tracing."""
    await inst.events.emit(
        type_, run_id=inst.state.run_id, subagent=_speaker_label(inst), **payload
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
        subagent=_speaker_label(inst),
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
