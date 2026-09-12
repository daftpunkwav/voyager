"""Long-running job worker: pulls from the queue, executes, and
emits progress / completion events.

Domains without long-running jobs can delete this file and drop their
long_running capabilities in capabilities.py.
"""

from __future__ import annotations

import asyncio

from platform_contracts import (
    ActorKind,
    ActorRef,
    DomainEvent,
    Event,
    JobStatus,
)
from platform_eventbus import EventBus

from .store import JobStore

_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="template.worker")


class Worker:
    """Bounded concurrency with on-demand start/stop. Extend with retry /
    backoff policies per domain needs."""

    def __init__(
        self,
        store: JobStore,
        bus: EventBus | None,
        queue: asyncio.Queue,
        *,
        concurrency: int = 1,
    ) -> None:
        self._store = store
        self._bus = bus
        self._queue = queue
        self._concurrency = concurrency
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        self._tasks = [asyncio.create_task(self._loop()) for _ in range(self._concurrency)]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def _loop(self) -> None:
        while True:
            job_id = await self._queue.get()
            await self._run_one(job_id)

    async def _run_one(self, job_id: str) -> None:
        await self._emit(DomainEvent.TASK_PROGRESS, job_id, progress=0.0)
        self._store.set_status(job_id, JobStatus.RUNNING.value)
        try:
            await asyncio.sleep(0.05)  # sample work: replace with real execution
            result = {"job_id": job_id, "echo": "done"}
            self._store.set_status(job_id, JobStatus.COMPLETED.value, result)
            await self._emit(DomainEvent.TASK_COMPLETED, job_id, result=result)
        except Exception as exc:  # noqa: BLE001  # persist + emit failure, never kill the worker
            self._store.set_status(job_id, JobStatus.FAILED.value, {"error": str(exc)})
            await self._emit(DomainEvent.TASK_FAILED, job_id, error=str(exc))

    async def _emit(self, type_: str, job_id: str, **payload) -> None:
        if self._bus is not None:
            await self._bus.publish(
                Event(type=type_, actor=_ACTOR, payload={"job_id": job_id, **payload})
            )
