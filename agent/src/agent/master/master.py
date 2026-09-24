"""Master agent: orchestration, arbitration, dispatch, and the team room.

- Multi-session: every chat session gets its own conversational instance,
  lock, and inbox (SessionManager owns identity + lifecycle); messages target
  a session explicitly or fall back to the active one;
- Arbitration: a new message while that session is running is queued
  (default) / merged / redirected per agent.arbiter.mode;
- Direct-chat mode (agent.direct_chat, off by default): simple Q/A is
  answered by the orchestrator directly, no session spawn;
- The resident host chat turn stays ReAct; persona default modes apply to
  dispatches and to member turns (@-mention / handoff — run_turn(member=));

This file keeps the user conversation turn, member-turn routing (@-mention,
inbox entries carrying a speaker), the task-board delivery/claim relays
(announce_delivery / notify_task_claim), arbitration, and public methods;
dispatch implementation lives in dispatch.py, session identity in sessions.py,
the board state machine in task_board.py.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from platform_contracts import DomainEvent, Event, ServiceError
from platform_eventbus import EventBus

from agent.contracts import DeliveryRun, SettingsReader
from agent.llm import LLMClient, content_to_text

if TYPE_CHECKING:
    from agent.master.dispatch import DeferredDispatch
from agent.master.arbiter import Arbiter, ArbiterMode
from agent.master.digest import DigestStore
from agent.master.sessions import CHAT_GOAL, SessionManager
from agent.master.synthesize import synthesize_result
from agent.master.task_board import TaskBoard
from agent.personas import PERSONAS, canonical_persona_key
from agent.policy import PolicyEngine
from agent.runtime.deadline import Deadline
from agent.runtime.evaluation import TaskEvaluator, record_evaluation
from agent.runtime.events import AGENT_MAIN
from agent.runtime.state import RunStatus
from agent.subagent import Spawner, SubagentInstance
from agent.subagent.limits import limits_from_settings

log = logging.getLogger("agent.master")


def _last_assistant_text(history: list[dict[str, Any]]) -> str:
    """Most recent non-empty assistant message of a turn (tool entries skipped)."""
    for message in reversed(history):
        if message.get("role") == "assistant":
            content = content_to_text(message.get("content")).strip()
            if content:
                return content
    return ""


def _eval_setting(settings: Any, key: str, default: Any) -> Any:
    """Read an evaluation setting through the single-arg SettingsReader.

    The store returns its registered default when unset; unknown keys
    (unregistered fakes in tests) fall back to the given default instead
    of failing the turn.
    """
    try:
        value = settings.get(key)
    except Exception:  # noqa: BLE001  # unknown key in fakes -> default, turn continues
        log.debug("evaluation setting %s unreadable, using default %r", key, default)
        return default
    return default if value is None else value


@dataclass
class _Queued:
    """One parked entry of a session inbox: a user message, a system notice,
    or a member turn (@-mention / handoff) waiting for the current turn to
    end. `member` names the persona that should speak this entry."""

    text: str
    guard: Callable[[], bool] | None = None
    member: str = ""


#: "@Elio 讲讲…" -> ("elio", "讲讲…"); "@elio:…" keeps the colon -> ("elio", ":…");
#: no match -> ("", text)
_MENTION_RE = re.compile(r"^@([A-Za-z][A-Za-z0-9_-]*)\s*", re.DOTALL)


def _parse_mention(text: str) -> tuple[str, str]:
    """Split a leading @-mention off a user message. Only resident team
    members route: unknown names, @lucien, and bare pings with nothing after
    the name stay with the host verbatim."""
    stripped = text.strip()
    m = _MENTION_RE.match(stripped)
    if m is None:
        return "", text
    key = canonical_persona_key(m.group(1).lower())
    if key not in PERSONAS or key == "orchestrator":
        return "", text
    rest = stripped[m.end() :].strip()
    if not rest:
        # A bare "@Name" carries nothing to hand over: a member turn without a
        # user message would send the LLM a request with no user role (invalid
        # on several providers) and leave the transcript assistant-tailed.
        return "", text
    return key, rest


def _guard_allows(guard: Callable[[], bool], session: str) -> bool:
    """Evaluate a notice turn's pre-step barrier. An exploding guard is
    fail-closed: the wakeup is skipped, never run unverified - a fence that
    cannot be checked must not be bypassed."""
    try:
        return bool(guard())
    except Exception:
        log.exception("pre-step guard failed (session %s); skipping the notice turn", session)
        return False


__all__ = ["CHAT_GOAL", "Master"]


class Master:
    def __init__(
        self,
        *,
        llm: LLMClient,
        bus: EventBus | None,
        spawner: Spawner,
        arbiter: Arbiter,
        digests: DigestStore,
        settings: SettingsReader,
        hooks=None,
        memory=None,
        subagents=None,  # SubagentRegistry: dispatch user-defined defs by name
        policy: PolicyEngine
        | None = None,  # global policy engine: copied when narrowing a user-defined subagent's network
        session_store=None,  # SessionStore: chat history persistence across restarts
        distiller=None,  # memory.Distiller: background extraction of durable memories
        wake_budget=None,  # runtime.wake_budget.WakeBudget: wakeup gate for notices
        goal_driver=None,  # master.goal_driver.GoalDriver: schedules continuation rounds
        organizer=None,  # skills.SkillOrganizer: repeated tool flows -> skill proposals
        task_graph=None,  # master.task_graph.TaskGraph: dependency edges between named tasks
        blackboard=None,  # master.blackboard.Blackboard: task-scoped shared notes
        task_board=None,  # master.task_board.TaskBoard: team publish/claim/confirm board
    ) -> None:
        self._llm = llm
        self._bus = bus
        self._spawner = spawner
        self._arbiter = arbiter
        self._digests = digests
        self._settings = settings
        self._hooks = hooks
        self._memory = memory
        self._subagents = subagents
        self._policy = policy
        self._session_store = session_store
        self._distiller = distiller
        self._organizer = organizer
        self._wake_budget = wake_budget
        self.goal_driver = goal_driver  # public: build attaches after construction
        # (single attribute: _start_turn reads this one, so a driver attached
        # post-construction via build.py is honored)
        self.task_graph = task_graph
        self.blackboard = blackboard
        self._task_board: TaskBoard | None = task_board
        # Strong references to background dispatch tasks: prevent the GC from
        # collecting a Task before completion, silently dropping its notifications
        self._bg: set[asyncio.Task] = set()
        # Per-session arbitration queues (feed/queue decisions land here while
        # that session's turn is running)
        self._inboxes: dict[str, deque[_Queued]] = {}
        self.sessions = SessionManager(
            spawner=spawner,
            sink_fn=self._session_sink,
            store=session_store,
            bus=bus,
            on_delete=self._drop_session_inbox,
        )

    def _drop_session_inbox(self, session_id: str) -> None:
        """Drop a deleted session's queued-message inbox: messages parked while
        its turn was running belong to the dead conversation and must never
        drain into a later session recreated with the same id."""
        self._inboxes.pop(session_id, None)

    # -- reply plumbing -------------------------------------------------------

    def _session_sink(self, session_id: str):
        """Per-session reply sink for conversational instances."""

        async def _sink(text: str, kind: str = "message", speaker: str = "") -> None:
            await self._reply(text, session=session_id, kind=kind, speaker=speaker)

        return _sink

    async def _reply(
        self,
        text: str,
        *,
        trace_id: str = "",
        session: str = "",
        kind: str = "message",
        speaker: str = "",
    ) -> None:
        """Publish one timeline message. `speaker` names the team member who
        is talking (persona key); empty = the resident host Lucien, which is
        also how every pre-team message reads back."""
        if self._bus is not None:
            payload: dict[str, Any] = {"content": text, "session": session, "kind": kind}
            if speaker:
                payload["speaker"] = speaker
            await self._bus.publish(
                Event(
                    type=DomainEvent.AGENT_MESSAGE,
                    actor=AGENT_MAIN,
                    payload=payload,
                    trace_id=trace_id,
                )
            )

    async def reply(
        self,
        text: str,
        *,
        trace_id: str = "",
        session: str = "",
        kind: str = "message",
        speaker: str = "",
    ) -> None:
        """Public reply outlet: modules split out of this file (dispatch etc.)
        route messages back through here instead of calling the private _reply."""
        await self._reply(text, trace_id=trace_id, session=session, kind=kind, speaker=speaker)

    # -- team delivery announcements --------------------------------------------

    async def announce_delivery(
        self,
        inst: DeliveryRun,
        *,
        ok: bool,
        result: str,
        error: str = "",
        trace_id: str = "",
    ) -> None:
        """One dispatched teammate finished: stamp the task board, publish the
        structured delivery card (agent.delivery), and wake the host so
        Lucien tells the user — the standing member reports to the speaker,
        who relays. Event-driven, not a sleep loop: this runs on the
        dispatch's own completion path. (Typed as the minimal DeliveryRun
        surface, so it also accepts any structurally matching run handle.)"""
        board_task_id = getattr(inst.task, "board_task_id", "") or ""
        # dispatch's cancel branches announce with error="cancelled": a stopped
        # run is not a failure, the row closes out through board.cancel so the
        # cancelled status (and not failed) is what the board view keeps.
        cancelled = (not ok) and error == "cancelled"
        if board_task_id and self._task_board is not None:
            with suppress(Exception):
                if cancelled:
                    self._task_board.cancel(board_task_id)
                else:
                    self._task_board.finish(board_task_id, ok=ok, result=result)
        member = inst.persona or inst.name
        started = inst.state.started_ts or 0.0
        elapsed = max(0, int(time.time() - started)) if started else 0
        # The card's title is the board row's task title: the run's goal is
        # the board BRIEF (what the member executes), so reading the goal
        # would render the brief as the card's title chip. Board-less runs
        # keep the goal text, and an evicted/missing row falls back too.
        title = (inst.task.goal or "")[:120]
        if board_task_id and self._task_board is not None:
            with suppress(Exception):
                title = str(self._task_board.get(board_task_id).get("title") or "")[:120] or title
        payload: dict[str, Any] = {
            "member": member,
            "name": inst.name,
            "title": title,
            "status": "done" if ok else "failed",
            "session": inst.task.session,
            "run_id": inst.state.run_id,
            "board_task_id": board_task_id,
        }
        if elapsed:
            payload["elapsed_s"] = elapsed
        if ok:
            payload["content"] = result
        else:
            payload["error"] = error or result[:500]
        if self._bus is not None:
            try:
                await self._bus.publish(
                    Event(
                        type=DomainEvent.AGENT_DELIVERY,
                        actor=AGENT_MAIN,
                        payload=payload,
                        trace_id=trace_id,
                    )
                )
            except Exception:
                # The card is the structured surface, not the completion itself:
                # a bus failure must not break the dispatch's completion path
                # (in the failure branch it would mask the original error, in the
                # cancelled branch replace the CancelledError) nor leak a
                # never-retrieved task exception. Same posture as the suppressed
                # board stamp above and the guarded relay below; the quiet
                # receipt / relay turn still tells the user.
                log.warning(
                    "delivery card failed to publish (session %s, run %s)",
                    inst.task.session,
                    inst.state.run_id,
                    exc_info=True,
                )
        # Lucien's one-line relay: a synthesized summary drives a notice turn
        # (the host is standing by, watching for teammates' reports). The
        # delivery card above is unconditional; the relay turn rides the
        # wake budget (job_notify's anti-self-excitation pattern) — over
        # budget it degrades to a quiet receipt so a burst of completions
        # cannot feed itself (the synthesis call stays behind the gate: an
        # over-budget burst must not spend LLM calls on discarded summaries).
        # A relay failure must never break the completion path either.
        sid = inst.task.session
        if self._wake_budget is not None and not self._wake_budget.allow(sid):
            try:
                await self.reply(
                    f"[team-report] {member} "
                    + ("已完成" if ok else "执行失败")
                    + ",详情见上方交付卡。",
                    trace_id=trace_id,
                    session=sid,
                    kind="notice",
                )
            except Exception:
                log.warning(
                    "quiet delivery receipt failed to publish (session %s)", sid, exc_info=True
                )
            return
        if self._wake_budget is not None:
            self._wake_budget.record(sid)
        if ok:
            summary = await synthesize_result(self._llm, member, result)
            body = (
                f"[team-report] 团队成员 {member} 已完成任务,汇报如下:{summary}\n"
                "请向用户简短播报这一结果(一两句,署成员的名),并给出下一步建议。"
            )
        else:
            body = (
                f"[team-report] 团队成员 {member} 的任务执行失败:{error or result[:300]}\n"
                "请向用户如实说明失败情况,并给出可选的下一步(重试/换人/放弃)。"
            )
        try:
            await self.handle_notice(sid, body, trace_id=trace_id)
        except Exception:
            log.warning(
                "team-report relay could not start a notice turn (session %s)",
                sid,
                exc_info=True,
            )

    async def notify_task_claim(self, task: dict, claimant: str, note: str) -> None:
        """A teammate claimed a board task: wake the publisher (Lucien) to
        either confirm the dispatch or answer the negotiation note — the
        standing speaker adjudicates, the teammate never dispatches itself."""
        session = str(task.get("session") or "")
        title = str(task.get("title") or "")
        task_id = str(task.get("id") or "")
        body = (
            f"[task-claim] 团队成员 {claimant} 认领了任务「{title}」({task_id})"
            + (f",留言:{note}" if note else "")
            + "\n请审阅:没问题就 taskboard(action=confirm, task_id) 拍板转入后台执行;"
            "成员有商议(要更多信息/容量不够)就先回应再定。"
        )
        try:
            await self.handle_notice(session, body)
        except Exception:
            log.warning(
                "task-claim relay could not start a notice turn (session %s)",
                session,
                exc_info=True,
            )

    # -- message flow -----------------------------------------------------------

    async def handle_user_message(
        self, text: str, *, trace_id: str = "", session_id: str = ""
    ) -> None:
        """User message entry point (dispatched by the event loop).

        Turn backgrounding: the new turn's work plus draining of queued
        messages run inside an asyncio.Task held in _bg, and this entry returns
        as soon as "queued / turn started" is decided - the EventLoop still
        serially awaits dispatch, but the user.message dispatch ends
        immediately, so a second message can enter arbitration while the first
        is still on the LLM instead of waiting out the whole ReAct turn.
        """
        if self._hooks is not None:
            await self._hooks.fire("on_user_message", text=text)
        if self._memory is not None:
            self._memory.working.add("user", text)
        if self._distiller is not None:
            distill = self._distiller.maybe_distill()
            if distill is not None:
                self.track_background(asyncio.create_task(distill))

        if self._settings.get(
            "agent.direct_chat"
        ):  # direct chat: no session, no subagent (off by default)
            self._start_direct(text, trace_id)
            return

        try:
            inst = self.sessions.resolve(session_id, seed_title=text)
        except ServiceError:
            # Unknown explicit session id: create it instead of losing the
            # message - clients may POST with a fresh id without a prior
            # create call, and a typo must not look like the agent ignoring
            # the user. Creation failures (bad id shape, session-count cap)
            # get a readable reply so the message never dies silently.
            try:
                created = self.sessions.create(session_id=session_id, title=text[:24])
            except ServiceError as exc:
                await self._reply(f"[无法创建会话] {exc.body.message}", trace_id=trace_id)
                return
            inst = self.sessions.resolve(created["session_id"])
        sid = inst.session
        if self._wake_budget is not None:
            self._wake_budget.reset(sid)  # real user input breaks any self-excitation chain
        member, mention_text = _parse_mention(text)
        if member:
            # The boss named a teammate directly: the named member takes the
            # floor (queued behind a running turn like any other speech)
            self._start_member_turn(inst, member, mention_text, trace_id)
            return
        if inst.status is RunStatus.RUNNING:
            mode = ArbiterMode(self._settings.get("agent.arbiter.mode"))
            decision = await self._arbiter.decide(text, inst.task.goal, mode=mode)
            if decision.action == "merge":
                inst.feed(text)  # merge into context; takes effect next turn
                return
            # Re-check after the arbiter await: the auto/guide judge is an LLM
            # call (seconds). If the turn ended while it ran, the RUNNING
            # snapshot above is stale and appending to the inbox would strand
            # the message until the NEXT user message triggers a drain. There
            # is no await between this check and the append/start below, so
            # the decision is atomic to the event loop.
            current = self.sessions.instance_for(sid)
            if current is None or current.status is not RunStatus.RUNNING:
                # current is None only if the session vanished meanwhile: fall back to
                # the instance resolved above instead of dropping the message
                self._start_turn(current if current is not None else inst, text, trace_id)
                return
        if inst.status is RunStatus.RUNNING:
            self._session_inbox(sid).append(_Queued(text))
            if decision.action == "enqueue_notify":
                await self._reply(f"[Queued] {decision.reason}", trace_id=trace_id, session=sid)
            return
        self._start_turn(inst, text, trace_id)

    async def handle_notice(
        self,
        session: str,
        text: str,
        *,
        trace_id: str = "",
        guard: Callable[[], bool] | None = None,
    ) -> None:
        """Internal wakeup: one turn driven by a system notice (background job
        completion, goal continuation). The notice rides the user-role channel
        with an explicit marker; it is not user speech, so working memory,
        hooks and the arbiter stay out of the path. A running turn simply
        queues the notice - notices never preempt and never start a second
        turn on the same session. `guard` is the sender's pre-step barrier:
        re-checked when the queued or admitted turn would actually start, so
        state that changed between reservation and start cancels the wakeup
        instead of running a stale continuation."""
        inst = self.sessions.resolve(session)
        if inst.status is RunStatus.RUNNING:
            self._session_inbox(inst.session).append(_Queued(text, guard))
            return
        self._start_turn(inst, text, trace_id, guard=guard)

    def _start_member_turn(
        self, inst: SubagentInstance, member: str, text: str, trace_id: str
    ) -> None:
        """Give the floor to a named teammate (@-mention): the turn runs under
        that persona over the shared transcript and its reply is attributed to
        them. A running turn queues the mention behind it, like any speech."""
        if inst.status is RunStatus.RUNNING:
            self._session_inbox(inst.session).append(_Queued(text, None, member))
            return
        self._start_turn(inst, text, trace_id, member=member)

    async def queue_member_turn(
        self, session: str, member: str, brief: str, *, trace_id: str = ""
    ) -> dict:
        """Hand a task to a resident teammate (subagent action=handoff): the
        member speaks a full turn once the current one ends, and the reply
        lands in the group timeline under their own name. Validation of the
        member key lives at the capability layer; unknown keys fail loudly."""
        inst = self.sessions.resolve(session)
        queued = inst.status is RunStatus.RUNNING
        if queued:
            self._session_inbox(inst.session).append(_Queued(brief, None, member))
        else:
            self._start_turn(inst, brief, trace_id, member=member)
        return {"member": member, "session": inst.session, "queued": queued}

    def _session_inbox(self, session_id: str) -> deque[_Queued]:
        box = self._inboxes.get(session_id)
        if box is None:
            box = deque()
            self._inboxes[session_id] = box
        return box

    def _start_direct(self, text: str, trace_id: str) -> None:
        """Direct-chat turn in the background: no instance, one completion."""

        async def _run() -> None:
            try:
                reply = await self._llm.complete(
                    [
                        {"role": "system", "content": PERSONAS["orchestrator"].system_prompt},
                        {"role": "user", "content": text},
                    ]
                )
                await self._reply(reply.text or "", trace_id=trace_id)
            except Exception as exc:
                log.exception("direct-chat turn failed")
                try:
                    await self._reply(f"(Turn failed: {exc})", trace_id=trace_id, kind="error")
                except Exception:
                    log.exception("publishing the turn-failure reply failed")

        self.track_background(asyncio.create_task(_run()))

    def _session_live(self, inst: SubagentInstance) -> bool:
        """Whether the session still resolves to this exact instance: a delete
        that raced a queued turn (status was not RUNNING yet) pops the cached
        instance while the backgrounded task still holds the old reference —
        running it would spend a full LLM turn on a deleted session and
        strand orphan replies in the log."""
        return self.sessions.instance_for(inst.session) is inst

    def _start_turn(
        self,
        inst: SubagentInstance,
        text: str,
        trace_id: str,
        *,
        guard: Callable[[], bool] | None = None,
        member: str = "",
    ) -> None:
        """Run the turn in the background: the entry returns immediately; the
        per-session lock guarantees only one turn writes that session at a
        time (different sessions may run concurrently within the scheduler's
        global cap). `guard` is re-evaluated once the lock is held (pre-step
        barrier): a False result cancels the turn before any LLM work.
        `member` hands the floor to a resident teammate for this turn."""

        async def _run() -> None:
            try:
                async with self.sessions.lock_for(inst.session):
                    if not self._session_live(inst):
                        # Deleted while this turn sat queued: drop it and the
                        # stale inbox (the session no longer exists).
                        self._inboxes.pop(inst.session, None)
                        return
                    if guard is not None and not _guard_allows(guard, inst.session):
                        log.info(
                            "pre-step guard cancelled the notice turn (session %s)",
                            inst.session,
                        )
                        return
                    await self._turn(inst, text, trace_id, member=member)
                    # Re-arm the goal continuation after every turn (primary
                    # and queued alike): an active goal keeps advancing until
                    # the agent marks it done/blocked; the driver's fence and
                    # daily round budget bound the loop.
                    if self.goal_driver is not None:
                        self.goal_driver.maybe_schedule(inst.session)
                    inbox = self._session_inbox(inst.session)
                    while inbox:  # queued messages are handled in order
                        queued = inbox.popleft()
                        if not self._session_live(inst):
                            # Session deleted mid-drain (status flickers
                            # WAITING_INPUT between queued turns): the rest of
                            # the queue belongs to a dead session.
                            self._inboxes.pop(inst.session, None)
                            break
                        if queued.guard is not None and not _guard_allows(
                            queued.guard, inst.session
                        ):
                            log.info(
                                "pre-step guard cancelled a queued notice (session %s)",
                                inst.session,
                            )
                            continue
                        if queued.member:
                            # A named teammate takes the floor for this entry;
                            # the rest of the queue keeps its order behind it
                            await self._turn(inst, queued.text, trace_id, member=queued.member)
                        else:
                            if self._memory is not None:
                                self._memory.working.add("user", queued.text)
                            await self._turn(inst, queued.text, trace_id)
                        if self.goal_driver is not None:
                            self.goal_driver.maybe_schedule(inst.session)
            except Exception as exc:
                # The turn is backgrounded: the EventLoop no longer awaits the
                # whole turn, so a failure must not become "Task exception was
                # never retrieved" (same semantics as loop isolation). It must
                # not become silence either: tell the user the turn died, or a
                # provider/infrastructure failure would look like the agent
                # simply ignoring the message.
                log.exception("user turn failed")
                try:
                    await self._reply(
                        f"(Turn failed: {exc})",
                        trace_id=trace_id,
                        session=inst.session,
                        kind="error",
                    )
                except Exception:
                    log.exception("publishing the turn-failure reply failed")

        self.track_background(asyncio.create_task(_run()))

    async def _turn(
        self, inst: SubagentInstance, text: str, trace_id: str, *, member: str = ""
    ) -> None:
        # Re-read round limits every turn: changes from the settings page apply
        # to the next message without restarting the conversation instance
        inst.apply_limits(limits_from_settings(self._settings))
        inst.deadline = Deadline.from_settings(self._settings)
        await self._spawner.start(inst, text, member=member)
        self._digests.upsert(inst)
        self.sessions.persist(inst.session)
        reply = _last_assistant_text(inst.history)
        if self._memory is not None and reply:
            # Working memory sees both sides of the exchange so distillation
            # can read what the agent actually answered, not only the asks
            self._memory.working.add("assistant", reply[:2000])
        # Turn evaluation and feedback recording (best effort: evaluation
        # must never fail the user turn).
        try:
            if _eval_setting(self._settings, "agent.evaluation.enabled", True):
                eval_mode = _eval_setting(self._settings, "agent.evaluation.mode", "heuristic")
                min_score = float(
                    _eval_setting(self._settings, "agent.evaluation.min_score_threshold", 0.6)
                )
                if eval_mode == "judge":
                    eval_res = await TaskEvaluator.evaluate_judge(
                        self._llm,
                        user_prompt=text,
                        assistant_reply=reply or "",
                        task_goal=inst.task.goal if inst.task else "",
                        min_score=min_score,
                    )
                else:
                    eval_res = TaskEvaluator.evaluate_heuristic(
                        user_prompt=text,
                        assistant_reply=reply or "",
                        steps=inst.state.steps if hasattr(inst, "state") and inst.state else None,
                        task_goal=inst.task.goal if inst.task else "",
                        min_score=min_score,
                    )
                if self._memory is not None:
                    record_evaluation(self._memory, eval_res, run_id=inst.id)
        except Exception:  # evaluation is best effort, never fails the turn
            log.warning("turn evaluation failed (turn result unaffected)", exc_info=True)
        if self._organizer is not None:
            proposal = self._organizer.maybe_propose()
            if proposal is not None:
                self.track_background(asyncio.create_task(proposal))

    def finish_task(self, name: str, *, ok: bool) -> None:
        """Join point of the task graph: release unblocked deferred tasks
        (re-dispatched in the background) and post a readable note for the
        ones blocked for good by a failed dependency."""
        if self.task_graph is None:
            return
        for release in self.task_graph.finish(name, ok=ok):
            if release.ok:
                self.track_background(asyncio.create_task(self._redispatch(release)))
            else:
                self.track_background(asyncio.create_task(self._blocked_note(release)))

    async def _redispatch(self, release) -> None:
        from agent.master.dispatch import dispatch_task

        await dispatch_task(
            self,
            self._spawner,
            self._settings,
            self._policy,
            self._subagents,
            self._hooks,
            **release.task.dispatch_args,
        )

    async def _blocked_note(self, release) -> None:
        await self.reply(f"[blocked] {release.task.name}: {release.reason}")

    # -- dispatch -----------------------------------------------------------------

    async def dispatch_task(
        self,
        goal: str,
        *,
        persona: str = "",
        mode: str | None = None,
        allowed_tools: tuple[str, ...] | None = None,
        readonly: bool = False,
        name: str = "",
        constraints: str = "",
        depends_on: tuple[str, ...] | None = None,
        board_task_id: str = "",
    ) -> SubagentInstance | DeferredDispatch:
        """Thin dispatch wrapper: implementation lives in dispatch.py, keeping
        Master the single external entry point. A task whose dependencies are
        still pending returns a DeferredDispatch instead of an instance."""
        from agent.master.dispatch import dispatch_task

        return await dispatch_task(
            self,
            self._spawner,
            self._settings,
            self._policy,
            self._subagents,
            self._hooks,
            goal,
            persona=persona,
            mode=mode,
            allowed_tools=allowed_tools,
            readonly=readonly,
            name=name,
            constraints=constraints,
            depends_on=depends_on,
            board_task_id=board_task_id,
        )

    # -- compat surface --------------------------------------------------------

    @property
    def chat(self) -> SubagentInstance | None:
        """The active session's instance (legacy single-conversation handle;
        None before the first turn or in direct-chat mode)."""
        return self.sessions.instance_for(self.sessions.active_id())

    @property
    def llm(self) -> LLMClient:
        """Chat client for split-out modules (dispatch notice synthesis);
        the same metered instance the master itself completes through."""
        return self._llm

    @property
    def digests(self) -> DigestStore:
        """Lets split-out modules read/write summary cards (without exposing
        private details)."""
        return self._digests

    def track_background(self, task: asyncio.Task) -> None:
        """Register a background dispatch task: strong reference against GC,
        removed automatically on completion."""
        self._bg.add(task)
        task.add_done_callback(self._bg.discard)
