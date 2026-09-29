"""Repo clone worker: git clone -> source.ready.

Clone targets live uniformly under `workspace/repo/<owner>__<name>`;
failures are persisted to the error field and emitted as task.failed.
A missing or broken git is reported honestly (never faked as success).
The clone function is injectable so tests stay offline.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path

from platform_contracts import ActorKind, ActorRef, DomainEvent, Event
from platform_eventbus import EventBus

from .._shared.paths import within
from .store import RepoStore

log = logging.getLogger("sources.repo.worker")

_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="sources.repo.worker")

#: (owner, name, dest) -> None; default implementation is git clone --depth 1
CloneFn = Callable[[str, str, Path], Awaitable[None]]

#: Worker-side re-validation of the store's owner/name: both the clone URL and
#: the destination directory (workspace/repo/<owner>__<name>, rmtree'd before
#: every clone) are derived from these by f-string. Import-time URL parsing
#: validates its own input, but store rows also originate from search results
#: or hand-edited data dirs — a component with path separators or a '..' run
#: must never shape a local path or a git argument.
_COMPONENT_RE = re.compile(r"[A-Za-z0-9._-]+")

#: Hard ceiling on one git clone. Without it a hung network / credential
#: prompt blocks communicate() forever, and with a single consumer and an
#: unbounded queue that stalls the whole repo import/remove pipeline.
_CLONE_TIMEOUT_S = 600.0


def _safe_component(kind: str, value: object) -> str:
    text = str(value or "")
    if not text or not _COMPONENT_RE.fullmatch(text) or ".." in text:
        raise RuntimeError(f"repo {kind} contains unsupported characters: {text!r}")
    return text


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
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=_CLONE_TIMEOUT_S)
    except TimeoutError:
        # Kill and reap, or the orphaned git keeps running past the timeout.
        proc.kill()
        await proc.communicate()
        raise RuntimeError(
            f"git clone timed out after {int(_CLONE_TIMEOUT_S)}s (possible network hang)"
        ) from None
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
            try:
                if isinstance(item, tuple) and item[0] == "remove":
                    await self._run_remove(item[2])
                else:
                    await self._run_one(item)
            except Exception as exc:  # the worker must not die on a single bad job
                log.warning("worker task failed: item=%r error=%s", item, exc, exc_info=True)

    async def _run_remove(self, local_path: str) -> None:
        """Delete the local clone directory (queued by remove_repo after the
        DB row is gone).

        Defense in depth: the enqueue side already jail-checked the stored
        path against the workspace root, but the rmtree here runs without any
        other validation and the queue can carry a stale row across a
        restart — so this side re-checks instead of trusting the enqueue-time
        gate.
        """
        if not local_path:
            return
        if not within(Path(local_path), self._root.parent):
            log.warning(
                "repo remove skipped: stored path %r is outside the workspace root",
                local_path,
            )
            return

        def _remove() -> None:
            shutil.rmtree(local_path, ignore_errors=True)

        # Disk deletion off the event loop: syncing rmtree on a cloned repo
        # (thousands of files) would stall the worker's loop, as in doc/worker
        await asyncio.to_thread(_remove)

    async def _run_one(self, rid: str) -> None:
        repo = self._store.get(rid, with_readme=False)
        if repo is None:
            return
        await self._emit(DomainEvent.TASK_PROGRESS, rid, progress=0.1, stage="clone")
        try:
            # Validate before any path or URL is derived (see _safe_component):
            # a rejected component fails the job with a persisted error instead
            # of rmtree/cloning through a crafted name.
            owner = _safe_component("owner", repo["owner"])
            name = _safe_component("name", repo["name"])
            dest = self._root / f"{owner}__{name}"
            if dest.exists():  # re-import: clear the old directory first
                # Off the event loop, same as _run_remove
                await asyncio.to_thread(shutil.rmtree, dest, True)
            await self._clone(owner, name, dest)
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
