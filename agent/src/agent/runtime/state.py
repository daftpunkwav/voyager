"""Run state and checkpoints: run/step state machine plus recoverable
checkpoint persistence.

Responsibilities:
- RunStatus/RunState/Step: the run/step state machine; alive statuses survive
  restarts
- ResumeSnapshot: the minimal data to rebuild a SubagentInstance (turn boundary or
  mid-turn)
- CheckpointStore: atomic save/load/delete plus startup sweeps (purge_tmp);
  run_id is sanitized before it touches file paths
- reclaim_alive / prepare_resumable_checkpoints: on restart, mark alive runs failed
  or pause resumable ones (no instances rebuilt here)
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# run_id goes directly into file paths, so only strictly safe characters are allowed
# (prevents ../../ escaping the checkpoints directory)
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _safe_run_id(run_id: str) -> str:
    if not _RUN_ID_RE.match(run_id):
        raise ValueError(
            f"invalid run_id: {run_id!r} (only letters/digits/underscore/hyphen allowed)"
        )
    return run_id


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"  # conversational subagent waiting for the user's next message
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def alive(self) -> bool:
        return self in (RunStatus.RUNNING, RunStatus.WAITING_INPUT, RunStatus.PAUSED)


@dataclass
class Step:
    n: int
    kind: str  # "llm" | "tool"
    name: str
    summary: str
    ts: float = field(default_factory=time.time)
    #: Structured step facts for tracing/UIs (tool_call_id, args, ok, ms,
    #: usage...); free-form per step kind, size-capped at build time.
    #: Defaults empty so pre-upgrade checkpoints (no such key) still load.
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResumeSnapshot:
    """Resume snapshot: the minimal set needed to rebuild a SubagentInstance.

    Stored in RunState.resume (dict form); checkpoints without this key are legacy and not
    resumable.
    """

    instance_id: str
    instance_name: str
    persona: str
    goal: str
    constraints: str = ""
    done_when: str = ""
    mode: str = "react"  # Mode.value
    allowed_tools: list[str] | None = None
    #: Read-only dispatch survives resume (defaults False so pre-upgrade
    #: snapshots without this key still load).
    readonly: bool = False
    #: Chat session this task was dispatched from (defaults empty so
    #: pre-multi-session snapshots still load); results route back to it.
    session: str = ""
    max_rounds: int | None = None
    max_tool_calls: int | None = None
    conversational: bool = False
    history: list[dict[str, Any]] = field(default_factory=list)
    active_tools: list[str] = field(default_factory=list)
    # mid-turn snapshot: the full in-flight ReAct messages (system / history / this turn's
    # tool rows included); None = a turn-boundary snapshot. Old tool text is already
    # truncated to the compress budget, and trailing unpaired tool groups rolled back.
    pending_messages: list[dict[str, Any]] | None = None
    in_turn: bool = False  # True = crashed mid-ReAct within the turn; resume continues, no new turn

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResumeSnapshot:
        return cls(**data)


@dataclass
class RunState:
    task: str
    subagent_id: str = ""
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: RunStatus = RunStatus.PENDING
    steps: list[Step] = field(default_factory=list)
    rounds: int = 0
    tool_calls: int = 0
    delegation_depth: int = (
        0  # nesting level of this instance (parent + 1); persists via checkpoint
    )
    result: str | None = None
    error: str = ""
    started_ts: float = field(default_factory=time.time)  # for instance duration display
    resume: dict[str, Any] | None = None  # ResumeSnapshot.to_dict(); None = legacy, not resumable

    def add_step(
        self, kind: str, name: str, summary: str, detail: dict[str, Any] | None = None
    ) -> Step:
        step = Step(
            n=len(self.steps) + 1, kind=kind, name=name, summary=summary, detail=dict(detail or {})
        )
        self.steps.append(step)
        return step

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunState:
        data = dict(data)
        data["status"] = RunStatus(data["status"])
        data["steps"] = [Step(**s) for s in data.get("steps", [])]
        data.setdefault("started_ts", 0.0)  # backward compatibility with old checkpoints
        return cls(**data)


class CheckpointStore:
    """data/runtime/checkpoints/<run_id>.json; the source of truth for crash recovery."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, state: RunState) -> Path:
        """Atomic write: write a temp file in the same directory first, then os.replace into
        place.

        The target path is not truncated before replace succeeds, so a mid-write crash leaves
        at most an orphan .tmp and never a half-written <run_id>.json (a half-written file
        would be skipped by list_alive and lose that checkpoint forever). All persistence
        paths (mid-save / end of turn) funnel through this method.
        """
        path = self._root / f"{_safe_run_id(state.run_id)}.json"
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
        tmp.write_text(json.dumps(state.to_dict(), ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
        return path

    def load(self, run_id: str) -> RunState:
        path = self._root / f"{_safe_run_id(run_id)}.json"
        return RunState.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_alive(self) -> list[RunState]:
        """List checkpoints still alive; a corrupt file is skipped without blocking other
        checkpoints or startup."""
        out = []
        for path in sorted(self._root.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                state = RunState.from_dict(raw)
            except (
                json.JSONDecodeError,
                UnicodeDecodeError,
                ValueError,
                KeyError,
                TypeError,
                OSError,
            ):
                continue
            if state.status.alive:
                out.append(state)
        return out

    def delete(self, run_id: str) -> None:
        (self._root / f"{_safe_run_id(run_id)}.json").unlink(missing_ok=True)

    def purge_tmp(self) -> int:
        """Startup sweep of orphan .tmp files left behind when save's atomic write crashed.

        Only the checkpoints root level (no recursion) and only files matching the save naming
        shape `.{run_id}.json.{8-hex}.tmp`; valid *.json and other .tmp files are untouched.
        At startup this process has no concurrent saves (writes only happen after assembly),
        so no mtime threshold is applied; multiple processes sharing one data/runtime
        directory is not a supported deployment. A single undeletable file (e.g. locked) is
        skipped without blocking startup and swept again on the next startup.
        """
        removed = 0
        for path in sorted(self._root.glob(".*.json.*.tmp")):
            if not path.is_file():
                continue
            try:
                path.unlink()
                removed += 1
            except OSError:
                continue
        return removed


def reclaim_alive(store: CheckpointStore) -> list[RunState]:
    """Startup reclaim: on process restart, mark all on-disk checkpoints still alive as
    failed.
    Mid-run resume is not implemented here and no instances are rebuilt from them; the failed
    states are returned for startup logging / caller awareness."""
    out: list[RunState] = []
    for state in store.list_alive():
        state.status = RunStatus.FAILED
        state.error = "process restarted, task not recovered"
        store.save(state)
        out.append(state)
    return out


def prepare_resumable_checkpoints(store: CheckpointStore) -> list[RunState]:
    """On process restart: alive checkpoints with a resume snapshot become PAUSED awaiting
    recovery; legacy ones without a snapshot stay FAILED (same as reclaim_alive).
    Returns the processed states for startup logging / caller awareness; no instances are
    rebuilt here (resume goes through the capability)."""
    out: list[RunState] = []
    for state in store.list_alive():
        if state.resume is not None:
            state.status = RunStatus.PAUSED
            state.error = "process restarted, resumable"
        else:
            state.status = RunStatus.FAILED
            state.error = "process restarted, task not recovered"
        store.save(state)
        out.append(state)
    return out
