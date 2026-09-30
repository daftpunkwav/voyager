"""Turn execution for a SubagentInstance: run_turn and its step/delta/event
callbacks (one file, one responsibility: the per-turn machinery).

`inst` is duck-typed (SubagentInstance); importing the class here would cycle
through the tools package. The instance keeps thin delegating methods so the
public surface (instance.run_turn, scheduler callbacks) is unchanged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING, Any

from platform_capability import current_chat_session
from platform_contracts import DomainEvent, RuntimeEvent

from agent.context.builder import TURN_CONTEXT_HEADER
from agent.context.editor import SUMMARY_MARK
from agent.engine.modes import ABORT_PREFIXES, Mode, ModeLimits, run_mode
from agent.personas import PERSONAS, Persona, resolve_persona
from agent.runtime.current import current_instance
from agent.runtime.state import RunStatus
from agent.runtime.trace import start_span
from agent.tools.core.activate import graded_toolbelt, infer_domains, page_preactivate

if TYPE_CHECKING:
    from agent.engine.instance import SubagentInstance

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


def _turn_context_row(
    inst: SubagentInstance, persona_key: str, user_text: str
) -> dict[str, Any] | None:
    """Build the trailing per-turn context row: bucketed usage status plus the
    volatile builder layers (memory cards, relevance recall, subagent digests,
    current page, plan gate).

    The row is a user-role message appended AFTER the full history, not a
    per-turn mutation inside the system prompt: a provider prefix cache is a
    byte-prefix of the whole request, so volatile content at the head would
    re-bill the entire history every turn, while at the tail it only re-bills
    itself. None when nothing has content (no context row is appended).
    """
    built = (
        inst.build_turn_context(inst.task, persona_key, user_text)
        if inst.build_turn_context is not None
        else ""
    )
    parts = "\n\n".join(p for p in (inst.context_status_line(), built) if p)
    inst._turn_context = built
    if not parts:
        return None
    return {"role": "user", "content": f"{TURN_CONTEXT_HEADER}\n\n{parts}"}


def _refresh_turn_context_row(messages: list[dict[str, Any]], row: dict[str, Any] | None) -> None:
    """Mid-turn resume: swap the snapshot's context row for a fresh one, so a
    resumed run sees current usage/digests. The snapshot row is replaced in
    place (same position keeps the message shape the loop expects).

    A snapshot without one (pre-feature checkpoint) gets the fresh row folded
    into the trailing plain user entry, row content first — never appended as
    a second user message when the snapshot ends on one: strict anthropic-
    format endpoints reject consecutive user turns and _anthropic_messages
    does not merge them. After any other tail shape (assistant / tool rows)
    the row still appends, which is a legal adjacency.

    Accepted fold cost: with the input buried under the marker prefix,
    prefix-keyed consumers (react's idle-continue check, the SUMMARY_MARK
    history write-back) treat the whole entry as context — when that turn
    also compacted mid-way, its original input text stays out of history.
    Bounded to a legacy-checkpoint resume; the alternative (a second user
    message) is a hard provider rejection, not a softer loss.

    Matching is user-role only: the marker check must never hit an assistant
    entry (a model echoing the marker) — replacing that with the context row
    would drop its tool_calls and break pairing."""
    for i, m in enumerate(messages):
        if m.get("role") == "user" and str(m.get("content") or "").startswith(TURN_CONTEXT_HEADER):
            if row is not None:
                messages[i] = row
            return
    if row is None:
        return
    last = messages[-1] if messages else None
    if last is not None and last.get("role") == "user" and not last.get("tool_calls"):
        # Row content first: the folded entry must keep the marker prefix so
        # react's idle-continue check and the history write-back still
        # recognize it as context, not user input.
        last["content"] = f"{row['content']}\n\n{last.get('content') or ''}"
        return
    messages.append(row)


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


def _build_turn_messages(
    inst: SubagentInstance, user_text: str | None, view: Persona | None, member_prompt: str
) -> list[dict[str, Any]]:
    """Assemble this turn's wire messages: system head + transcript view +
    trailing per-turn context row.

    Two shapes: a mid-turn resume continues from the snapshot's messages
    (pending history already inside; the system entry is recomputed so
    style/profile changes apply to the resume, and the snapshot's context
    row is swapped for a fresh one) — resume carries no new input, the only
    entry point resume_run->start passes no user_text. Otherwise the history
    is rebuilt fresh: the turn's input is appended first, then the shared
    transcript view, then the context row.
    """
    if inst.resume_messages and view is None:
        messages = [dict(m) for m in inst.resume_messages]
        inst.resume_messages = None
        if messages and messages[0].get("role") == "system":
            messages[0] = inst._system_message()
        _refresh_turn_context_row(messages, _turn_context_row(inst, inst.persona, user_text or ""))
        return messages
    if user_text:
        inst.history.append({"role": "user", "content": user_text})
    messages = [
        inst._system_message(member_prompt),
        *_transcript_view(inst.history),
    ]
    row = _turn_context_row(inst, view.key if view is not None else inst.persona, user_text or "")
    if row is not None:
        messages.append(row)
    return messages


def _surrender_reason(inst: SubagentInstance, step_base: int) -> str:
    """The budget-exhaustion stamp among THIS turn's steps (empty when the
    turn ended normally). The scan is scoped to steps[step_base:] because
    state.steps is never cleared: an unscoped reverse scan would re-stamp an
    older turn's reason onto the current one."""
    for step in reversed(inst.state.steps[step_base:]):
        if step.kind == "system" and step.name == "surrender":
            return str((step.detail or {}).get("reason") or "")
    return ""


def _write_back_compaction(
    inst: SubagentInstance,
    messages: list[dict[str, Any]],
    covered: list[dict[str, Any]],
) -> None:
    """Persist mid-turn compaction into the shared history: the summary has
    replaced the condensed middle, so writing the wire view back keeps later
    turns from re-summarizing the same span.

    `covered` is the delivery provenance run_mode reports back (react fills
    it): wire entries whose text the closing message carries verbatim. They
    are excluded here BY IDENTITY — the closing message is appended right
    after, so a covered entry would otherwise double up in history. The mode
    owns the knowledge of what its delivery was assembled from; this side
    never re-infers it from text shapes.

    _transcript_view folds a teammate's speaker into a leading 【display
    name】 prefix and keeps the wire view key-clean, so the key never
    survives onto these messages: recover it here (display name -> persona
    key) and strip the prefix again, so history keeps its invariant "raw
    text + optional speaker" and the next turn's view prefixes exactly once.
    The trailing turn-context row is transient per-turn state: it never
    enters history (the next turn renders a fresh one).
    """
    rebuilt: list[dict[str, Any]] = []
    by_display = {p.display_name: k for k, p in PERSONAS.items()}
    for m in messages[1:]:  # skip system; tool entries and empty tool-turn text stay out of history
        role = m.get("role")
        if role == "user":
            text = str(m.get("content", ""))
            if text.startswith(TURN_CONTEXT_HEADER):
                continue
            rebuilt.append({"role": "user", "content": text})
        elif role == "assistant":
            # A wire entry the closing delivery was assembled from (identity
            # match against the mode-reported provenance) rides in the
            # closing message and must not double up
            if any(m is c for c in covered):
                continue
            text = str(m.get("content", ""))
            if text:
                entry: dict[str, Any] = {"role": "assistant", "content": text}
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
    # Cancelled while queued for a concurrency slot: the deferred coroutine
    # must stop here instead of rewriting CANCELLED back to RUNNING and
    # running to completion once the slot opens (start()'s entry check only
    # covers cancels that land before start was called).
    if inst.state.status is RunStatus.CANCELLED:
        # Conversational closure: the queued message would otherwise get no
        # reply at all (the sink is success-only), and master._turn would read
        # the PREVIOUS turn's assistant text out of history as this turn's
        # reply. Same notice shape as the CancelledError branch below.
        if inst.task.conversational and inst.reply_sink is not None:
            try:
                await inst.reply_sink(
                    "[已取消] 本回合尚未开始即被取消;可重新发送或换个说法继续。",
                    "notice",
                    speaker=view.key if view is not None else "",
                )
            except Exception:  # best effort: the cancel itself is unaffected
                log.debug("failed to emit pre-start cancel closure message", exc_info=True)
        return "[cancelled] 已在开始执行前被取消,未执行任何步骤。"
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
    # Fresh turn: drop any previous turn's cap-surrender stamp (it must not
    # claim this turn), and remember the step-trail length so the finally's
    # reverse scan only sees THIS turn's steps — state.steps is never cleared,
    # so an unscoped scan would re-stamp an older turn's reason here.
    inst.state.surrender_reason = ""
    step_base = len(inst.state.steps)
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
        # Rebuild the system prompt every turn so style/profile/skill
        # changes never go stale across turns; the turn's input rides along
        # as the memory read policy's recall query (the relevance layer),
        # and page/digest state renders into the per-turn context row
        inst.system_prompt = inst.build_system(inst.task, inst.persona, user_text or "")
    messages = _build_turn_messages(inst, user_text, view, member_prompt)
    inst._turn_messages = messages  # live reference for mid-turn snapshots (on_step)
    turn_belt = inst.toolbelt
    if view is not None and view.tool_allow is not None:
        # Member turn: the teammate works on its own curated surface (trimmed
        # view, never written back — the resident host keeps its full table)
        turn_belt = inst.toolbelt.trimmed(view.tool_allow)
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
        turn_belt = graded_toolbelt(
            inst.toolbelt,
            inst.active,
            preactivate=tuple(preactivate),
        )
    # Prefix-cache diagnostics: fold this turn's request head; a changed
    # segment emits one debug line on the "agent.context.prefix" logger. The
    # tool segment hashes the ACTIVE specs (what the wire actually carries),
    # schema bytes included — a graded-activation change is a real tools-segment
    # cache break and must not be misread as provider-side.
    specs = turn_belt.specs()
    inst.prefix_watch.observe(
        system=str(messages[0].get("content") or "") if messages else "",
        tools=[spec.name for spec in specs],
        tool_fingerprint=json.dumps(
            [[spec.name, spec.description, spec.schema] for spec in specs],
            ensure_ascii=False,
            sort_keys=True,
        ),
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
            # Delivery provenance the mode fills in (which wire entries the
            # closing message carries): the compaction write-back excludes
            # exactly those instead of re-inferring the delivery's shape
            delivery: dict[str, Any] = {"covered": []}
            try:
                member_mode = Mode(view.default_mode) if view is not None else None
            except ValueError:  # broken mode in a persona file: ride react
                member_mode = None
            result = await run_mode(
                member_mode or inst.task.mode or Mode.REACT,
                llm=inst.llm,
                toolbelt=turn_belt,
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
                conversational=inst.task.conversational,
                delivery_meta=delivery,
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
            # Cooperative pause: stop at a paired boundary, persist a
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
                # Live continue_run rides the same pending view: the
                # in-process resume path reads resume_messages (the snapshot
                # below serves the after-restart path). Task instances only —
                # a conversational resume would arrive with fresh user input,
                # which the resume branch of _build_turn_messages does not
                # carry; chat pauses rebuild from history like before.
                if not inst.task.conversational:
                    inst.resume_messages = messages
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
            # Conversational closure: same rationale as the cancel branch — the
            # reply sink is success-only and the chat UI clears its typing
            # state on agent.message, so a paused turn that returns before the
            # closing append would leave the exchange hanging forever. Task
            # dispatches announce the pause through their own [paused] reply.
            if inst.task.conversational and inst.reply_sink is not None:
                try:
                    await inst.reply_sink(
                        "[已暂停] 已在当前步骤完成后暂停并保存检查点;恢复后继续。",
                        "notice",
                        speaker=view.key if view is not None else "",
                    )
                except Exception:  # best effort: the pause itself is unaffected
                    log.debug("failed to emit pause closure message", exc_info=True)
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
            # Budget-exhaustion endings return normally; stamp the reason so
            # wait/dispatch callers can tell a truncated run from a real one
            inst.state.surrender_reason = _surrender_reason(inst, step_base)
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
            # will not re-summarize the same history; without the write-back every
            # turn would re-condense the same history.
            _write_back_compaction(inst, messages, delivery["covered"])
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
                # Three delivery kinds, decided by what the turn actually was:
                # degraded LLM text (quota / provider failure placeholders) is
                # an error, a harness wind-down ([中断]/[预算]/[无工具可用] —
                # the caps spoke, not the model) is a system warning, and
                # everything else is a normal answer. The latest llm step
                # carries the degraded flag, so read it back instead of
                # sniffing prefixes for that one.
                if _turn_degraded(inst):
                    kind = "error"
                elif result.startswith(ABORT_PREFIXES):
                    kind = "warning"
                else:
                    kind = "message"
                try:
                    await inst.reply_sink(
                        result,
                        kind,
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
    payload: dict[str, Any] = {
        "run_id": inst.state.run_id,
        "subagent": _speaker_label(inst),
        "session": inst.session,
        "name": name,
        "kind": kind,
        "summary": (summary or "")[:120],
        "detail": detail or {},
    }
    if kind == "tool":
        # Tool steps carry the tool's own classification (dimension/write, the
        # same vocabulary the roster publishes): downstream attribution reads
        # the stamp so renaming or adding tools cannot silently drop events.
        # Additive payload fields — older consumers ignore them.
        payload.update(inst.toolbelt.step_stamp(name))
    await inst.events.emit(DomainEvent.AGENT_STEP, **payload)
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
