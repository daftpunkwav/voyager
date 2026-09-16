"""Scheduler for graph index jobs: concurrency cap, retries,
backoff.

Responsibilities:
- Poll the queue and run jobs under a concurrency semaphore
- Retry failed jobs up to an attempts cap with exponential backoff
- Emit task.progress / task.completed / task.failed events on the bus

A single scheduler plus a concurrency semaphore is enough for local tooling
scale. Retry means re-enqueueing via finish(retry=True) with an attempts cap.
When the queue is empty the loop simply idles.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from platform_contracts import ActorKind, ActorRef, DomainEvent, Event
from platform_eventbus import EventBus

from .index_queue import IndexQueue

_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="graph.scheduler")

#: (job) -> None; raise on failure, the scheduler decides retry/abandon by attempts
RunJobFn = Callable[[dict[str, Any]], Awaitable[None]]


class IndexScheduler:
    def __init__(
        self,
        queue: IndexQueue,
        run_job: RunJobFn,
        bus: EventBus | None = None,
        *,
        concurrency: int = 1,
        max_attempts: int = 3,
        backoff_base_s: float = 1.0,
        idle_poll_s: float = 0.5,
    ) -> None:
        self._queue = queue
        self._run = run_job
        self._bus = bus
        self._sem = asyncio.Semaphore(concurrency)
        self._max_attempts = max_attempts
        self._backoff = backoff_base_s
        self._poll = idle_poll_s
        self._task: asyncio.Task | None = None
        self._running: set[asyncio.Task] = set()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        for t in self._running:
            t.cancel()
        if self._running:
            await asyncio.gather(*self._running, return_exceptions=True)

    async def _loop(self) -> None:
        while True:
            job = self._queue.next()
            if job is None:
                await asyncio.sleep(self._poll)  # idle while the queue is empty
                continue
            task = asyncio.create_task(self._run_guarded(job))
            self._running.add(task)
            task.add_done_callback(self._running.discard)

    async def _run_guarded(self, job: dict[str, Any]) -> None:
        async with self._sem:
            await self._emit(DomainEvent.TASK_PROGRESS, job, progress=0.0, stage="start")
            try:
                await self._run(job)
            except asyncio.CancelledError:
                self._queue.finish(job["id"], ok=False, error="cancelled")
                raise
            except Exception as exc:  # noqa: BLE001  # a job failure must not kill the scheduler
                retry = job["attempts"] < self._max_attempts
                if retry:
                    await asyncio.sleep(self._backoff * (2 ** (job["attempts"] - 1)))
                self._queue.finish(job["id"], ok=False, error=str(exc), retry=retry)
                await self._emit(
                    DomainEvent.TASK_FAILED if not retry else DomainEvent.TASK_PROGRESS,
                    job,
                    error=str(exc)[:200],
                    stage="retry" if retry else "failed",
                )
                return
            self._queue.finish(job["id"], ok=True)
            await self._emit(DomainEvent.TASK_COMPLETED, job, progress=1.0)

    async def _emit(self, type_: str, job: dict[str, Any], **payload) -> None:
        if self._bus is not None:
            await self._bus.publish(
                Event(
                    type=type_,
                    actor=_ACTOR,
                    payload={"job_id": job["id"], "project": job["project"], **payload},
                )
            )
