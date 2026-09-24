"""Task board: the team's publish / claim / confirm state machine.

Lucien publishes a task after scoping it with the user; a resident teammate
claims it (optionally with a note — more info needed, too much on their
plate); Lucien confirms the claim and the task flips to a dispatched run.
Pure in-memory state, one instance per process, lifetime matching the
dispatched instances themselves (a restart loses running tasks the same way
it loses them). No Master dependency: the board only stores and transitions;
wiring (what a confirm actually spawns) lives at the capability layer.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from platform_contracts import ErrorSuffix, ServiceError

_DOMAIN = "agent"

#: open -> claimed -> assigned -> running -> done/failed; cancelled from any
#: live state. Terminal rows are kept for the session's board view.
_OPEN = "open"
_CLAIMED = "claimed"
_ASSIGNED = "assigned"
_RUNNING = "running"
_DONE = "done"
_FAILED = "failed"
_CANCELLED = "cancelled"

_STATUS = (_OPEN, _CLAIMED, _ASSIGNED, _RUNNING, _DONE, _FAILED, _CANCELLED)

_MAX_TASKS = 50
_MAX_TEXT = 2000


@dataclass
class BoardTask:
    """One row of the team's task board."""

    id: str
    title: str
    brief: str
    session: str
    publisher: str  # persona key of the publisher (the host: "orchestrator")
    status: str = _OPEN
    claimant: str | None = None  # persona key of the claiming teammate
    claim_note: str | None = None  # negotiation note attached to the claim
    run_id: str | None = None  # dispatched instance's run, set on confirm/start
    result: str | None = None  # terminal summary (delivery text / error)
    created_ts: float = 0.0
    updated_ts: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "brief": self.brief,
            "session": self.session,
            "publisher": self.publisher,
            "status": self.status,
            "claimant": self.claimant,
            "claim_note": self.claim_note,
            "run_id": self.run_id,
            "result": self.result,
            "created_ts": self.created_ts,
            "updated_ts": self.updated_ts,
        }


def _now() -> float:
    return time.time()


class TaskBoard:
    """Thread-safe in-memory board; every mutation returns the row's dict."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, BoardTask] = {}

    # -- queries --------------------------------------------------------------

    def list(self, session: str = "", status: str = "") -> list[dict[str, Any]]:
        """Rows newest-first; `session` / `status` narrow when given."""
        with self._lock:
            rows = [
                t.to_dict()
                for t in self._tasks.values()
                if (not session or t.session == session) and (not status or t.status == status)
            ]
        rows.sort(key=lambda r: r["created_ts"], reverse=True)
        return rows

    def get(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"no such task: {task_id}")
            return task.to_dict()

    # -- transitions ----------------------------------------------------------

    def publish(self, *, title: str, brief: str, session: str, publisher: str) -> dict[str, Any]:
        """Open a task on the board (the host announces it in the group)."""
        task = BoardTask(
            id=f"t-{uuid.uuid4().hex[:6]}",
            title=title[:_MAX_TEXT],
            brief=brief[:_MAX_TEXT],
            session=session,
            publisher=publisher,
            created_ts=_now(),
            updated_ts=_now(),
        )
        with self._lock:
            if len(self._tasks) >= _MAX_TASKS:
                oldest = min(self._tasks.values(), key=lambda t: t.created_ts)
                del self._tasks[oldest.id]
            self._tasks[task.id] = task
            return task.to_dict()

    def claim(self, task_id: str, *, claimant: str, note: str = "") -> dict[str, Any]:
        """A teammate raises a hand; `note` carries the negotiation message
        (more info needed / capacity concerns). Re-claim by the same member
        updates the note; a second member gets a readable conflict."""
        with self._lock:
            task = self._require(task_id)
            if task.status == _OPEN:
                pass
            elif task.status == _CLAIMED and task.claimant == claimant:
                pass  # refresh own note
            else:
                raise ServiceError(
                    _DOMAIN,
                    ErrorSuffix.CONFLICT,
                    f"task {task_id} is {task.status}"
                    + (f" (claimed by {task.claimant})" if task.claimant else ""),
                    hint="pick an open task, or discuss the assignment with the publisher",
                )
            task.status = _CLAIMED
            task.claimant = claimant
            task.claim_note = note[:_MAX_TEXT] if note else None
            task.updated_ts = _now()
            return task.to_dict()

    def confirm(self, task_id: str, *, publisher: str) -> dict[str, Any]:
        """The publisher locks the claim in; the capability layer spawns the
        run and stamps run_id afterwards (mark_running)."""
        with self._lock:
            task = self._require(task_id)
            if task.publisher != publisher:
                raise ServiceError(
                    _DOMAIN,
                    ErrorSuffix.FORBIDDEN,
                    f"task {task_id} was published by {task.publisher}",
                )
            if task.status != _CLAIMED:
                raise ServiceError(
                    _DOMAIN,
                    ErrorSuffix.CONFLICT,
                    f"task {task_id} is {task.status}, not claimed",
                )
            task.status = _ASSIGNED
            task.updated_ts = _now()
            return task.to_dict()

    def mark_running(self, task_id: str, *, run_id: str) -> dict[str, Any]:
        with self._lock:
            task = self._require(task_id)
            if task.status not in (_ASSIGNED, _RUNNING):
                raise ServiceError(
                    _DOMAIN, ErrorSuffix.CONFLICT, f"task {task_id} is {task.status}"
                )
            task.status = _RUNNING
            task.run_id = run_id
            task.updated_ts = _now()
            return task.to_dict()

    def finish(self, task_id: str, *, ok: bool, result: str = "") -> dict[str, Any]:
        """Terminal transition from any live state (dispatch outcome)."""
        with self._lock:
            task = self._require(task_id)
            if task.status in (_DONE, _FAILED, _CANCELLED):
                return task.to_dict()
            task.status = _DONE if ok else _FAILED
            task.result = result[:_MAX_TEXT]
            task.updated_ts = _now()
            return task.to_dict()

    def cancel(self, task_id: str) -> dict[str, Any]:
        """Cancel from any live state; terminal rows (done/failed/cancelled)
        stay as they are."""
        with self._lock:
            task = self._require(task_id)
            if task.status in (_DONE, _FAILED, _CANCELLED):
                return task.to_dict()
            task.status = _CANCELLED
            task.result = "cancelled"
            task.updated_ts = _now()
            return task.to_dict()

    def reopen(self, task_id: str) -> dict[str, Any]:
        """Drop the claim and put the task back up (failed run, negotiation
        dead-end); the claim note stays for context."""
        with self._lock:
            task = self._require(task_id)
            if task.status in (_DONE, _FAILED, _CANCELLED, _RUNNING):
                raise ServiceError(
                    _DOMAIN, ErrorSuffix.CONFLICT, f"task {task_id} is {task.status}"
                )
            task.status = _OPEN
            task.claimant = None
            task.updated_ts = _now()
            return task.to_dict()

    # -- helpers --------------------------------------------------------------

    def _require(self, task_id: str) -> BoardTask:
        task = self._tasks.get(task_id)
        if task is None:
            raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"no such task: {task_id}")
        return task


def normalize_status(status: str) -> str:
    """Public vocabulary check for list filters; unknown falls to '' (all)."""
    return status if status in _STATUS else ""


__all__ = ["BoardTask", "TaskBoard", "normalize_status"]
