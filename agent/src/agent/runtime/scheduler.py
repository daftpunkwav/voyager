"""Scheduling: subagent concurrency cap, named-task tracking, one-shot
timers (reminders), and the durable-job dispatch loop with completion
notification (delivery preference per job kind; the listener is injected —
this module stays free of master/session vocabulary).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger("agent.scheduler")


class Scheduler:
    """In-process scheduler. Subagents are not microservices: concurrency is controlled
    with a semaphore."""

    def __init__(self, max_concurrent: int = 3) -> None:
        self._sem = asyncio.Semaphore(max_concurrent)
        self._max_concurrent = max_concurrent  # for observability; avoids Semaphore internals
        self._tasks: dict[str, asyncio.Task] = {}
        self._timers: dict[str, asyncio.Task] = {}
        self._job_handlers: dict[str, Callable[[dict], Awaitable[Any]]] = {}
        self._notify_prefs: dict[str, str] = {}  # kind -> "none" | "quiet" | "wakeup"
        self._completion_listener: Any = None  # async (job, ok, error, pref); injected
        self._queue_store: Any = None
        self._queue_task: asyncio.Task | None = None

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    async def run(self, name: str, coro: Awaitable[Any]) -> Any:
        """Run a named task within the concurrency cap.

        When the same name is reused, the new task overwrites the old registry entry: cleanup
        compares by task identity before removing, so an old task finishing later cannot
        remove the new task's registration (cancellation/observability therefore target the
        correct task).
        """
        async with self._sem:
            task = asyncio.current_task()
            if task is not None:
                self._tasks[name] = task
            try:
                return await coro
            finally:
                if self._tasks.get(name) is task:
                    self._tasks.pop(name, None)

    def call_later(self, delay: float, fn: Callable[[], Awaitable[Any]], *, name: str = "") -> str:
        """One-shot timer (follow-up/reminder); returns a cancellable timer id."""
        timer_id = name or uuid.uuid4().hex[:8]

        async def _fire() -> None:
            try:
                await asyncio.sleep(delay)
                await fn()
            except asyncio.CancelledError:
                raise
            except Exception:  # isolate timer callback failures: log, never crash the loop
                log.exception("scheduled callback failed: %s", timer_id or fn)
            finally:
                self._timers.pop(timer_id, None)

        self._timers[timer_id] = asyncio.create_task(_fire())
        return timer_id

    # -- durable queue: storage in runtime.queue_store, dispatch
    # policy here. Handlers map job kinds to coroutines; rows survive restarts.

    def register_job_handler(
        self, kind: str, fn: Callable[[dict], Awaitable[Any]], *, notify: str = "none"
    ) -> None:
        """Map a job kind to its executor (re-registered fresh at every boot;
        the queue rows are the durable part). `notify` selects the completion
        delivery: "none" (the handler itself was the visible effect), "quiet"
        (a notice message), or "wakeup" (a notice that may start a turn,
        budget-gated by the injected listener)."""
        self._job_handlers[kind] = fn
        self._notify_prefs[kind] = notify

    def set_completion_listener(self, fn: Any) -> None:
        """Install the completion listener: async (job, ok, error, pref). The
        scheduler only reports; what a notice or a wakeup means is the
        listener's vocabulary."""
        self._completion_listener = fn

    async def start_queue(self, store: Any, *, poll_interval: float = 5.0) -> None:
        """Start the due-job poll loop (idempotent: a running loop is kept)."""
        if self._queue_task is not None and not self._queue_task.done():
            return
        self._queue_store = store

        async def _loop() -> None:
            while True:
                try:
                    await self._run_due_jobs()
                except asyncio.CancelledError:
                    raise
                except Exception:  # a bad row/handler must not kill the loop
                    log.exception("queue tick failed")
                await asyncio.sleep(poll_interval)

        self._queue_task = asyncio.create_task(_loop())

    async def _run_due_jobs(self) -> None:
        store = self._queue_store
        if store is None:
            return
        for job in store.due():
            store.mark_started(job.id)
            handler = self._job_handlers.get(job.kind)
            try:
                if handler is None:
                    raise LookupError(f"no handler registered for job kind {job.kind!r}")
                await self.run(f"job:{job.id}", handler(dict(job.payload)))
                store.mark_done(job.id)
                await self._report(job, ok=True, error="")
            except Exception as exc:  # noqa: BLE001  # one failed job never blocks the queue
                log.warning("job %s failed: %s", job.id, exc)
                detail = f"{type(exc).__name__}: {exc}"
                store.mark_failed(job.id, detail)
                await self._report(job, ok=False, error=detail)

    async def _report(self, job: Any, *, ok: bool, error: str) -> None:
        """Hand one finished job to the injected listener; the listener's own
        failure must not re-enter the retry path (delivery is best-effort)."""
        pref = self._notify_prefs.get(job.kind, "none")
        if pref == "none" or self._completion_listener is None:
            return
        try:
            await self._completion_listener(job, ok, error, pref)
        except Exception:
            log.exception("completion listener failed (job %s)", job.id)

    async def stop_queue(self) -> None:
        if self._queue_task is not None:
            self._queue_task.cancel()
            try:
                await self._queue_task
            except asyncio.CancelledError:
                pass
            self._queue_task = None

    def cancel_timer(self, timer_id: str) -> bool:
        task = self._timers.pop(timer_id, None)
        if task is not None:
            task.cancel()
            return True
        return False

    def active(self) -> list[str]:
        return sorted(self._tasks)

    async def cancel(self, name: str) -> bool:
        task = self._tasks.pop(name, None)
        if task is not None:
            task.cancel()
            return True
        return False

    async def shutdown(self) -> None:
        """Cancel all in-flight tasks and await their reaping; exceptions do not escape
        (the shutdown path never raises)."""
        tasks = [*self._tasks.values(), *self._timers.values()]
        if self._queue_task is not None:
            tasks.append(self._queue_task)
            self._queue_task = None
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
