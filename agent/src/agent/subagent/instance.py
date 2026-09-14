"""Subagent instance: the state machine for one run.

Responsibilities:
- Own one run's SubStatus machine and its bounded cross-turn history
  (budget.history_max, dropped in pairs)
- run_turn(): execute one mode via modes.run_mode with that turn's toolbelt view
- Emit step/stream events through RuntimeEvents; persist checkpoints at turn and
  mid-turn points
- feed() is the arbiter's merge-into-context entry; apply_limits/rebind_toolbelt
  apply runtime changes to a live instance

Conversational instances return to WAITING_INPUT after each run_turn reply,
awaiting the next user message; task instances run to completion. feed()
is the arbiter's "merge into context" entry point.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from agent.context.backoff import CompactionBackoff
from agent.context.budgets import ContextBudget
from agent.context.compressor import compress
from agent.context.governor import ContextGovernor
from agent.context.prefix_watch import PrefixWatch
from agent.context.usage import (
    ContextWindow,
    UsageTracker,
    render_status_line,
    usage_status,
)
from agent.llm import LLMClient
from agent.runtime.events import RuntimeEvents
from agent.runtime.state import ResumeSnapshot, RunState, RunStatus
from agent.subagent import turn
from agent.subagent.modes import Mode, ModeLimits
from agent.tools.core.activate import (
    page_preactivate,  # noqa: F401  # compat re-export (old import path; locked by tests)
)
from agent.tools.core.base import Toolbelt


def _paired_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shallow-copy and roll back to the last paired boundary (tool pairs are
    never split).

    A crash mid multi-tool turn can leave messages ending in a partial group
    (assistant with tool_calls whose tool entries are incomplete); the
    endpoint requires pairing, so the partial tail is dropped whole - those
    calls never produced reusable results, and re-running them on resume is
    not duplication. Same accounting as compressor._prune_span: only tool
    entries **consecutive** after an assistant entry count.
    """
    out = [dict(m) for m in messages]
    for i in range(len(out) - 1, -1, -1):
        m = out[i]
        if m.get("role") == "assistant" and m.get("tool_calls"):
            j = i + 1
            while j < len(out) and out[j].get("role") == "tool":
                j += 1
            if j - i - 1 < len(m["tool_calls"]):
                del out[i:]
            break
    return out


class SubStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TaskBook:
    """Task book: goal, constraints, completion criteria, mode, capability
    surface, and round limits."""

    goal: str
    constraints: str = ""
    done_when: str = ""
    mode: Mode | None = None  # None -> persona default / REACT
    allowed_tools: tuple[str, ...] | None = None  # None = no trimming; () = no tools
    #: Read-only tasks: after trimming, every write/irreversible tool is
    #: dropped as well (review/audit work carries no write tools by
    #: construction, never by prompt constraint); never widens the surface.
    readonly: bool = False
    limits: ModeLimits | None = None
    conversational: bool = False
    #: Chat session this task belongs to; results route back to that session's
    #: timeline (empty = session-less background work, global lane).
    session: str = ""
    #: Task names that must complete before this one starts (parent-child
    #: tree only — no DAG engine). Empty = start immediately.
    depends_on: tuple[str, ...] = ()


@dataclass
class SubagentInstance:
    task: TaskBook
    toolbelt: Toolbelt
    llm: LLMClient
    system_prompt: str
    events: RuntimeEvents
    state: RunState
    reply_sink: Callable[[str], Awaitable[None]] | None = None
    name: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    history: list[dict[str, Any]] = field(default_factory=list)
    usage: UsageTracker = field(default_factory=UsageTracker)
    # Provider-reported input usage of the most recent call; anchors the
    # context status (estimate alone lags the real prefix size)
    pages: Any | None = None  # PageContextRegistry: per-domain page preactivation
    active: set[str] | None = (
        None  # tool activation set for conversational instances (kept across turns)
    )
    persona: str = ""  # persona key captured at spawn; needed for per-turn system rebuild
    parent_run_id: str = ""  # dispatching instance's id (cancel cascade); "" = top-level
    build_system: Callable[[TaskBook, str, str], str] | None = None
    # (task, persona key, turn input) -> system prompt; the third argument
    # feeds the memory read policy's resident relevance layer
    deadline: Any | None = (
        None  # runtime.deadline.Deadline (wall-clock caps), set by master per turn
    )
    pause_requested: bool = False  # cooperative pause: honored between steps (turn.py)
    # System-rebuild function injected by the spawner, called fresh each turn
    # in run_turn, so style/profile/page/digest/skill-index changes apply to
    # the very next message; no builder reference held, avoiding a circular import
    sync_digest: Callable[..., None] | None = None
    # Refreshes the DigestStore as steps happen; duck-typed, digest.py not imported
    checkpoint_persist: Callable[[SubagentInstance], None] | None = None
    # Mid-run persistence injected by the spawner (= checkpoints.save(state));
    # when absent (directly built instances / older wiring) _on_step skips mid-saves
    resume_messages: list[dict[str, Any]] | None = None
    # Mid-turn resume payload brought back from a snapshot by
    # resume_from_checkpoint; when present run_turn skips history rebuild and
    # continues from the next complete after the crash point
    budget: ContextBudget = field(default_factory=ContextBudget)
    # Context budget (history bound + per-turn compaction budget); injected
    # by the spawner from settings so operators tune both without code
    compaction_backoff: CompactionBackoff = field(default_factory=CompactionBackoff)
    # Compaction-failure guard (per instance): after repeated failing editor
    # rounds, compaction takes the deterministic path instead of re-spending
    # the planner call; lives here because the governor is rebuilt per call
    prefix_watch: PrefixWatch = field(default_factory=PrefixWatch)
    # Prompt prefix stability sentinel (per instance): one debug line per
    # changed head segment, for operators auditing provider prefix-cache
    # behavior ("agent.context.prefix" logger)
    #: Optional lighter client for the context editor's planning call
    #: (context_planner purpose routing, injected by the spawner); None =
    #: share the chat client as before
    planner_llm: LLMClient | None = None
    _turn_messages: list[dict[str, Any]] | None = field(default=None, init=False, repr=False)
    # Live reference to the in-turn ReAct messages (run_mode appends in place);
    # _on_step uses it to capture mid-turn snapshots, cleared when the turn ends

    @property
    def status(self) -> RunStatus:
        return self.state.status

    @property
    def session(self) -> str:
        """Chat session this instance belongs to (single source of truth:
        the task book; '' = session-less background work, global lane)."""
        return self.task.session

    def build_resume_snapshot(
        self,
        *,
        in_turn: bool = False,
        pending_messages: list[dict[str, Any]] | None = None,
    ) -> ResumeSnapshot:
        """Collect a resume snapshot from the current instance state.

        pending_messages=None produces a turn-boundary snapshot (same behavior
        as before); passing the current messages produces a mid-turn snapshot:
        pair-fix first, then truncate old tool text under the compress budget
        (same accounting, truncation only, no pruning) so oversized results
        are never written to disk unbounded.
        """
        pending = (
            compress(
                _paired_messages(pending_messages),
                budget=self.budget.compress_budget,
                prune=False,
            )
            if pending_messages is not None
            else None
        )
        return ResumeSnapshot(
            instance_id=self.id,
            instance_name=self.name,
            persona=self.persona,
            goal=self.task.goal,
            constraints=self.task.constraints,
            done_when=self.task.done_when,
            mode=(self.task.mode or Mode.REACT).value,
            allowed_tools=(
                list(self.task.allowed_tools) if self.task.allowed_tools is not None else None
            ),
            readonly=self.task.readonly,
            session=self.task.session,
            parent_run_id=self.parent_run_id,
            max_rounds=self.task.limits.max_rounds if self.task.limits else None,
            max_tool_calls=self.task.limits.max_tool_calls if self.task.limits else None,
            conversational=self.task.conversational,
            history=[dict(m) for m in self.history],
            active_tools=sorted(self.active) if self.active else [],
            pending_messages=pending,
            in_turn=in_turn,
        )

    async def run_turn(self, user_text: str | None = None) -> str:
        """Run one turn; the machinery lives in subagent.turn (one file, one
        responsibility)."""
        return await turn.run_turn(self, user_text)

    def _system_message(self) -> dict[str, Any]:
        """System entry: persona layers plus the per-turn context status line.

        The status travels inside the one system message (a second system row
        would be pruned like ordinary content by the compressor), rebuilt each
        turn so the model always sees current window facts and can compact
        proactively before heavy work.
        """
        status = usage_status(
            ContextWindow(
                window_tokens=self.budget.window_tokens,
                max_output_tokens=self.budget.max_output_tokens,
            ),
            self.history,
            self.usage,
            auto_compact_at=self.budget.auto_compact_at,
        )
        line = render_status_line(status, session=self.session)
        return {"role": "system", "content": f"{self.system_prompt}\n\n{line}"}

    def context_view(self) -> list[dict[str, Any]]:
        """The live transcript: in-turn messages while running, else the
        cross-turn history. Public surface for the context meta tools
        (context_status / compact_context) and the human capability path."""
        return self._turn_messages if self._turn_messages is not None else self.history

    def governor(self) -> ContextGovernor:
        """Per-turn context authority from the spawn-time budget snapshot;
        rebuilt per call so callers never hold a stale one."""
        return ContextGovernor(
            window=ContextWindow(
                window_tokens=self.budget.window_tokens,
                max_output_tokens=self.budget.max_output_tokens,
            ),
            auto_compact_at=self.budget.auto_compact_at,
            compact_target=self.budget.compact_target,
            fallback_budget=self.budget.compress_budget,
            tracker=self.usage,
            llm=self.llm,
            planner=self.planner_llm,
            guard=self.compaction_backoff,
        )

    def feed(self, text: str) -> None:
        """Arbiter merge path: merge new input directly into this instance's
        context."""
        self.history.append({"role": "user", "content": text})

    def rebind_toolbelt(self, toolbelt: Toolbelt) -> None:
        """Adjust the tool surface at assembly time (e.g. narrower network tier
        on dispatch); never swapped while running."""
        self.toolbelt = toolbelt

    def apply_limits(self, limits: ModeLimits) -> None:
        """Adjust round/tool limits (e.g. derived tier when direct-chat toggles)."""
        self.task = replace(self.task, limits=limits)

    def last_step_summary(self) -> str:
        """Summary of the most recent step (source for the summary card; empty
        string when there are no steps)."""
        return self.state.steps[-1].summary if self.state.steps else ""

    def _bound_history(self) -> None:
        """When over the history bound (budget.history_max), drop the oldest
        turns from the head in pairs.

        History holds only alternating user/assistant entries, so dropping an
        even count keeps the head a user entry - no partial assistant-led turn
        leaks into the next round.
        """
        over = len(self.history) - self.budget.history_max
        if over > 0:
            del self.history[: (over + 1) // 2 * 2]

    def cancel(self) -> None:
        self.state.status = RunStatus.CANCELLED

    # -- turn machinery delegates (bodies live in subagent.turn) --------------

    async def _on_delta(self, round_n: int, text: str) -> None:
        return await turn.on_delta(self, round_n, text)

    async def _on_event(self, type_: str, **payload: Any) -> None:
        return await turn.on_event(self, type_, **payload)

    async def _on_step(
        self, kind: str, name: str, summary: str, detail: dict[str, Any] | None = None
    ) -> None:
        return await turn.on_step(self, kind, name, summary, detail)

    def _mid_save_checkpoint(self) -> None:
        turn.mid_save_checkpoint(self)
