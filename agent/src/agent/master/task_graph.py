"""Task graph: dependency edges and join points between named tasks
(parent-child tree only — a full DAG engine is out of scope by design).

A deferred task registers with the names it waits on; when a task finishes,
`finish()` clears it from every waiting set and returns the release
decisions: satisfied tasks are re-dispatched, tasks whose dependency FAILED
are dropped with a deterministic reason (never silently stuck). Pure state,
no IO and no dispatching — the master owns both.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_MAX_PENDING = 50


@dataclass
class DeferredTask:
    """One task held back until its dependencies resolve."""

    name: str
    dispatch_args: dict[str, Any] = field(default_factory=dict)  # exactly dispatch_task(**args)
    waiting_on: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Release:
    task: DeferredTask
    ok: bool  # False = a dependency failed; the task is dropped, not run
    reason: str = ""


class TaskGraph:
    def __init__(self) -> None:
        self._deferred: dict[str, DeferredTask] = {}
        self._finished_ok: set[str] = set()

    def pending(self, name: str, *, depends_on: tuple[str, ...]) -> set[str]:
        """Register (or extend) the waiting set for a task name; returns the
        dependencies still outstanding (empty = run now). Already-finished
        dependencies count as satisfied."""
        waiting = {d for d in depends_on if d and d not in self._finished_ok}
        if not waiting:
            return set()
        if name not in self._deferred and len(self._deferred) >= _MAX_PENDING:
            raise RuntimeError("too many deferred tasks")
        existing = self._deferred.get(name)
        if existing is not None:
            existing.waiting_on |= waiting
        else:
            self._deferred[name] = DeferredTask(name=name, waiting_on=waiting)
        return waiting

    def stash_args(self, name: str, dispatch_args: dict[str, Any]) -> None:
        """Remember the exact dispatch call to replay when released."""
        task = self._deferred.get(name)
        if task is not None:
            task.dispatch_args = dict(dispatch_args)

    def finish(self, name: str, *, ok: bool) -> list[Release]:
        """A named task reached a terminal state: return every deferred task
        this unblocks (ok=True) or blocks for good (ok=False)."""
        if ok:
            self._finished_ok.add(name)
        releases: list[Release] = []
        for task in list(self._deferred.values()):
            if name not in task.waiting_on:
                continue
            task.waiting_on.discard(name)
            if not ok:
                self._deferred.pop(task.name, None)
                releases.append(Release(task=task, ok=False, reason=f"dependency {name} failed"))
            elif not task.waiting_on:
                self._deferred.pop(task.name, None)
                releases.append(Release(task=task, ok=True))
        return releases

    def waiting_on(self) -> dict[str, tuple[str, ...]]:
        """Read-only snapshot for visibility (instance lists, diagnostics)."""
        return {t.name: tuple(sorted(t.waiting_on)) for t in self._deferred.values()}


__all__ = ["DeferredTask", "Release", "TaskGraph"]
