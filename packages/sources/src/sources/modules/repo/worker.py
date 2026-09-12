"""Repo clone worker: git clone -> source.ready.

Clone targets live uniformly under `workspace/repo/<owner>__<name>`;
failures are persisted to the error field and emitted as task.failed.
A missing or broken git is reported honestly (never faked as success).
The clone function is injectable so tests stay offline.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path

from platform_contracts import ActorKind, ActorRef, DomainEvent, Event
from platform_eventbus import EventBus

from .store import RepoStore

_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="sources.repo.worker")

#: (owner, name, dest) -> None; default implementation is git clone --depth 1
CloneFn = Callable[[str, str, Path], Awaitable[None]]


async def _git_clone(owner: str, name: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        "git",
        "clone",
        "--depth",
        "1",
        f"https://github.com/{owner}/{name}.git",
        str(dest),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"git clone failed: {stderr.decode(errors='replace')[:300]}")


class RepoWorker:
    def __init__(
        self,
        store: RepoStore,
        bus: EventBus | None,
        queue: asyncio.Queue,
        workspace: Path,
        *,
        clone_fn: CloneFn | None = None,
    ) -> None:
        self._store = store
        self._bus = bus
        self._queue = queue
        self._root = Path(workspace) / "repo"
        self._clone = clone_fn or _git_clone
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _loop(self) -> None:
        while True:
            item = await self._queue.get()
            # Clone jobs are str(rid); removal jobs are ("remove", rid, local_path)
            if isinstance(item, tuple) and item[0] == "remove":
                await self._run_remove(item[2])
            else:
                await self._run_one(item)

    async def _run_remove(self, local_path: str) -> None:
        """Delete the local clone directory (queued by remove_repo after the
        DB row is gone).
        """
        if local_path:
            shutil.rmtree(local_path, ignore_errors=True)

    async def _run_one(self, rid: str) -> None:
        repo = self._store.get(rid, with_readme=False)
        if repo is None:
            return
        await self._emit(DomainEvent.TASK_PROGRESS, rid, progress=0.1, stage="clone")
        try:
            dest = self._root / f"{repo['owner']}__{repo['name']}"
            if dest.exists():  # re-import: clear the old directory first
                shutil.rmtree(dest, ignore_errors=True)
            await self._clone(repo["owner"], repo["name"], dest)
            self._store.set_status(rid, "ready", local_path=str(dest))
            await self._emit(DomainEvent.TASK_PROGRESS, rid, progress=1.0, stage="done")
            await self._emit(
                DomainEvent.SOURCE_READY,
                rid,
                kind="repo",
                name=f"{repo['owner']}/{repo['name']}",
                repo=f"{repo['owner']}/{repo['name']}",
                local_path=str(dest),
            )
        except Exception as exc:  # noqa: BLE001  # persist failure, never kill the worker
            self._store.set_status(rid, "failed", error=str(exc)[:500])
            await self._emit(DomainEvent.TASK_FAILED, rid, error=str(exc)[:300])

    async def _emit(self, type_: str, rid: str, **payload) -> None:
        if self._bus is not None:
            await self._bus.publish(
                Event(type=type_, actor=_ACTOR, payload={"source_id": rid, **payload})
            )
