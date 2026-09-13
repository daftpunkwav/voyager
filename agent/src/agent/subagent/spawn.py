"""Dispatch: capability-surface trimming + mode grant + limits assembly.

Responsibilities:
- spawn/start: build the TaskBook-bound instance (trimmed toolbelt, persona
  system prompt), track it in instances, and launch it via the scheduler
- resume_from_checkpoint: rebuild an instance from a persisted checkpoint
  (rebuild only, no re-run; an explicit resume continues it)
- cancel: stop a running instance by id or name
- Evict oldest terminal instances beyond TERMINAL_INSTANCE_CAP so the in-process
  registry stays bounded (alive/PENDING never evicted)

"Cannot write files" is not a prompt constraint - after trimmed() the write_file
tool is genuinely absent from the tool table.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from platform_contracts import ErrorSuffix, RuntimeEvent, ServiceError

from agent.context.budgets import ContextBudget
from agent.llm import LLMClient
from agent.runtime.events import RuntimeEvents
from agent.runtime.scheduler import Scheduler
from agent.runtime.state import CheckpointStore, ResumeSnapshot, RunState, RunStatus
from agent.subagent.instance import Mode, ModeLimits, SubagentInstance, TaskBook
from agent.tools.core.base import Toolbelt

log = logging.getLogger("agent.subagent.spawn")

# (task book, persona key, turn input) -> system prompt; the third argument
# is the text driving the current turn ("" at spawn/resume time) and feeds
# the memory read policy's resident relevance layer
BuildSystemFn = Callable[[TaskBook, str, str], str]


def _default_build_system(task: TaskBook, persona: str, query: str = "") -> str:
    return task.goal


#: Resident cap for terminal instances (runtime hygiene): when COMPLETED /
#: FAILED / CANCELLED instances exceed this count, the oldest by insertion
#: order are evicted so a long-running process's instances dict stays bounded.
#: A hardcoded constant, not a settings key; alive / PENDING instances are
#: never evicted - PENDING instances are still queued and eviction would lose
#: pending work.
TERMINAL_INSTANCE_CAP = 32
_TERMINAL_STATUSES = frozenset({RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED})


class Spawner:
    def __init__(
        self,
        *,
        llm: LLMClient,
        toolbelt: Toolbelt,
        scheduler: Scheduler,
        events: RuntimeEvents,
        checkpoints: CheckpointStore | None = None,
        build_system: BuildSystemFn | None = None,
        pages=None,  # PageContextRegistry: conversational instances preactivate tools per current page
        sync_digest=None,  # refreshes the DigestStore as steps happen; duck-typed
        budget_fn: Callable[[], ContextBudget] | None = None,  # hot-read context budget per spawn
        planner_llm: LLMClient | None = None,  # context editor planning client; None = chat llm
    ) -> None:
        self._llm = llm
        self._planner_llm = planner_llm
        self._toolbelt = toolbelt
        self._scheduler = scheduler
        self._events = events
        self._checkpoints = checkpoints
        self._build_system = build_system or _default_build_system
        self._pages = pages
        self._sync_digest = sync_digest
        self._budget_fn = budget_fn
        self.instances: dict[str, SubagentInstance] = {}

    def _budget(self) -> ContextBudget:
        """Current context budget: hot-read via the injected fn; absence of an
        fn (older wiring / direct builds) keeps the built-in defaults."""
        return self._budget_fn() if self._budget_fn is not None else ContextBudget()

    def _persist_checkpoint(self, inst: SubagentInstance) -> None:
        """checkpoint_persist injection target: same save semantics as start()'s finally."""
        if self._checkpoints is not None:
            self._checkpoints.save(inst.state)

    def _narrowed_belt(self, task: TaskBook) -> Toolbelt:
        """Trim + read-only narrowing, shared by spawn and resume rebuilds
        so a revived instance carries exactly the dispatched surface."""
        belt = self._toolbelt.trimmed(task.allowed_tools)
        if task.readonly:
            # Narrowing only: review tasks lose every write/irreversible tool
            # even when the allowlist (or a future preset) names one.
            belt = belt.trimmed_read_only()
        return belt

    def spawn(
        self,
        task: TaskBook,
        *,
        persona: str = "",
        name: str = "",
        reply_sink=None,
    ) -> SubagentInstance:
        toolbelt = self._narrowed_belt(task)
        instance = SubagentInstance(
            task=task,
            toolbelt=toolbelt,
            llm=self._llm,
            planner_llm=self._planner_llm,
            system_prompt=self._build_system(task, persona, ""),
            events=self._events,
            state=RunState(task=task.goal),
            reply_sink=reply_sink,
            name=name or task.goal[:16],
            pages=self._pages,
            persona=persona,
            build_system=self._build_system,  # rebuild system each turn
            sync_digest=self._sync_digest,  # refresh DigestStore on steps
            checkpoint_persist=self._persist_checkpoint,  # mid-run persistence
            budget=self._budget(),  # hot-read settings at spawn time
        )
        self.instances[instance.id] = instance
        return instance

    async def start(self, instance: SubagentInstance, user_text: str | None = None) -> str:
        """Start the instance within the scheduler's concurrency cap; persist a
        turn-boundary snapshot when the turn ends.

        Incremental mid-ReAct persistence is handled by instance._on_step;
        the finally here persists the turn-terminal (done/failed/cancelled)
        boundary snapshot, which overrides the mid-run snapshot and resets
        in_turn to False.
        """
        try:
            return await self._scheduler.run(instance.id, instance.run_turn(user_text))
        finally:
            if self._checkpoints is not None:
                instance.state.resume = instance.build_resume_snapshot().to_dict()
                self._checkpoints.save(instance.state)
            # The turn has terminated (success or failure): evict oldest terminal
            # instances when over the residency cap
            self._trim_terminal_instances()

    def resume_from_checkpoint(self, run_id: str) -> SubagentInstance:
        """Rebuild an instance from a checkpoint: task-mode REACT, non-conversational.

        Rebuild only, no re-run: the instance enters self.instances with state
        exactly as persisted (PAUSED after boot), waiting for an explicit
        resume (resume_run continue_run=true); the original run_id / steps /
        started_ts are preserved.
        """
        if self._checkpoints is None:
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND, "checkpoint storage is not enabled")
        for inst in self.instances.values():
            if inst.state.run_id == run_id and inst.status.alive:
                raise ServiceError(
                    "agent",
                    ErrorSuffix.INVALID_INPUT,
                    f"run {run_id} already has a live instance; duplicate resume is not allowed",
                    hint="use list_subagents to inspect running instances",
                )
        try:
            state = self._checkpoints.load(run_id)
        except (FileNotFoundError, ValueError) as exc:
            raise ServiceError(
                "agent", ErrorSuffix.NOT_FOUND, f"checkpoint not found: {run_id}"
            ) from exc
        if state.resume is None:
            raise ServiceError(
                "agent",
                ErrorSuffix.NOT_FOUND,
                f"checkpoint {run_id} has no resume snapshot (legacy), cannot resume",
            )
        try:
            snap = ResumeSnapshot.from_dict(state.resume)
        except TypeError as exc:  # snapshot missing/extra keys or non-dict: bad data -> ServiceError, no bare raise
            raise ServiceError(
                "agent",
                ErrorSuffix.NOT_FOUND,
                f"checkpoint {run_id} resume snapshot is corrupt, cannot resume",
            ) from exc
        if snap.conversational:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                "conversational instances are out of resume scope (the main conversation does not resume)",
            )
        if snap.mode != Mode.REACT.value:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"mode {snap.mode} is out of resume scope (react only)",
            )
        if state.status not in (RunStatus.PAUSED, RunStatus.WAITING_INPUT, RunStatus.RUNNING):
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"status {state.status.value} is not resumable (completed/failed/cancelled)",
            )
        limits = None
        if snap.max_rounds is not None or snap.max_tool_calls is not None:
            fallback = ModeLimits()
            limits = ModeLimits(
                max_rounds=snap.max_rounds if snap.max_rounds is not None else fallback.max_rounds,
                max_tool_calls=(
                    snap.max_tool_calls
                    if snap.max_tool_calls is not None
                    else fallback.max_tool_calls
                ),
            )
        task = TaskBook(
            goal=snap.goal,
            constraints=snap.constraints,
            done_when=snap.done_when,
            mode=Mode(snap.mode),
            allowed_tools=tuple(snap.allowed_tools) if snap.allowed_tools is not None else None,
            # Read-only survives resume: a revived review task must not
            # regain write tools through the rebuild.
            readonly=snap.readonly,
            # The dispatching session survives resume so results still route
            # back to that timeline.
            session=snap.session,
            limits=limits,
            conversational=snap.conversational,
        )
        instance = SubagentInstance(
            task=task,
            toolbelt=self._narrowed_belt(task),
            llm=self._llm,
            planner_llm=self._planner_llm,
            system_prompt=self._build_system(task, snap.persona, ""),
            events=self._events,
            state=state,  # exactly as persisted: run_id / steps / started_ts / status all preserved
            reply_sink=None,
            name=snap.instance_name,
            pages=self._pages,
            persona=snap.persona,
            build_system=self._build_system,  # rebuild system each turn on resume (same source as spawn)
            sync_digest=self._sync_digest,
            budget=self._budget(),
        )
        instance.history = [dict(m) for m in snap.history]
        if snap.active_tools:
            instance.active = set(snap.active_tools)
        if snap.in_turn and snap.pending_messages:
            # Mid-turn resume: the crash hit mid-ReAct of this turn;
            # pending_messages are carried back as-is and run_turn continues
            # from the next complete; missing/empty falls back to the earlier
            # behavior (history rebuild + fresh turn)
            pending = snap.pending_messages
            if not isinstance(pending, list) or not all(isinstance(m, dict) for m in pending):
                raise ServiceError(
                    "agent",
                    ErrorSuffix.NOT_FOUND,
                    f"checkpoint {run_id} resume snapshot is corrupt, cannot resume",
                )
            instance.resume_messages = [dict(m) for m in pending]
        instance.id = (
            snap.instance_id
        )  # force-restore the id; a new id would duplicate in instances
        self.instances[instance.id] = instance
        return instance

    def alive(self) -> list[SubagentInstance]:
        return [i for i in self.instances.values() if i.status.alive]

    def _trim_terminal_instances(self) -> list[str]:
        """When terminal instances exceed TERMINAL_INSTANCE_CAP, evict the
        oldest by insertion order.

        Only COMPLETED / FAILED / CANCELLED are touched; alive
        (RUNNING/WAITING_INPUT/PAUSED) and PENDING (queued, not yet run) are
        never evicted. Eviction is semantic termination: the evicted run's
        checkpoint file is deleted too (terminal checkpoints are not
        resumable - list_alive filters by status.alive - so the file would
        only be dead weight). Returns the evicted instance ids (for test
        assertions).
        """
        terminal_ids = [
            iid for iid, inst in self.instances.items() if inst.status in _TERMINAL_STATUSES
        ]
        overflow = len(terminal_ids) - TERMINAL_INSTANCE_CAP
        evicted = terminal_ids[:overflow] if overflow > 0 else []
        for iid in evicted:
            inst = self.instances.pop(iid, None)
            if inst is None or self._checkpoints is None:
                continue
            try:
                self._checkpoints.delete(inst.state.run_id)
            except OSError as exc:
                # Best effort (e.g. a file-locked JSON on Windows): registry
                # eviction still stands; the orphan file is inert (never
                # listed as resumable, never reloaded into the registry).
                log.warning(
                    "checkpoint delete failed for evicted run %s: %s", inst.state.run_id, exc
                )
        return evicted

    async def cancel(self, id_or_name: str) -> list[str]:
        """Emergency stop: cancel alive instances by id or name (conversational
        chat included), cascading down the spawn tree to the target's running
        descendants (instances it dispatched, transitively).

        The CANCELLED status is set before interrupting the underlying task -
        CancelledError inside run_turn is a BaseException, so an
        ``except Exception`` cannot swallow it and rewrite the status. Returns
        the stopped instance ids (target first, then descendants); empty list
        when nothing matched.
        """
        hits = [
            i for i in self.instances.values() if i.status.alive and id_or_name in (i.id, i.name)
        ]
        stopped: list[SubagentInstance] = []
        stopped_ids: set[str] = set()
        queue = list(hits)
        while queue:
            inst = queue.pop(0)
            if inst.id in stopped_ids:
                continue
            stopped_ids.add(inst.id)
            inst.cancel()
            await self._events.emit(
                RuntimeEvent.AGENT_CANCELLED,
                run_id=inst.state.run_id,
                subagent=inst.id,
                name=inst.name,
            )
            stopped.append(inst)
            # cascade: everything still running under this instance
            queue.extend(
                other
                for other in self.instances.values()
                if other.status.alive
                and other.id not in stopped_ids
                and other.parent_run_id == inst.id
            )
        for sid in stopped_ids:
            await self._scheduler.cancel(sid)
        # Emergency stop lands in CANCELLED: evict oldest terminal instances when over the cap
        self._trim_terminal_instances()
        return [i.id for i in stopped]


__all__ = ["Mode", "Spawner", "SubagentInstance", "TaskBook"]
