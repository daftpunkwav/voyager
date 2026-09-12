"""Doc parse worker: parse queue -> sections persisted -> source.ready.

Mirrors the RepoWorker queue pattern: CPU-heavy extraction runs in a
thread pool so the event loop stays responsive; parse_fn is injectable so
tests never touch real parsers. Removal jobs share the parse queue to
preserve ordering.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Callable
from pathlib import Path

from platform_contracts import ActorKind, ActorRef, DomainEvent, Event
from platform_eventbus import EventBus

from .extract import ExtractError, Section, extract_sections
from .store import DocStore

_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="sources.doc.worker")

#: (path, ext) -> list[Section]; default implementation calls extract_sections
ParseFn = Callable[[Path, str], list[Section]]


def _default_parse(path: Path, ext: str) -> list[Section]:
    return extract_sections(path, ext)


class DocWorker:
    def __init__(
        self,
        store: DocStore,
        bus: EventBus | None,
        queue: asyncio.Queue,
        workspace: Path,
        *,
        parse_fn: ParseFn | None = None,
    ) -> None:
        self._store = store
        self._bus = bus
        self._queue = queue
        self._parse = parse_fn or _default_parse
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
            # Parse jobs are str(doc_id); removal jobs are ("remove", doc_id, local_path)
            try:
                if isinstance(item, tuple) and item[0] == "remove":
                    await self._run_remove(item[1], item[2])
                else:
                    await self._run_one(item)
            except Exception as exc:  # the worker must not die on a single bad job
                import logging

                logging.getLogger("sources.doc.worker").warning(
                    "worker task failed: item=%r error=%s", item, exc, exc_info=True
                )

    async def _run_remove(self, did: str, local_path: str) -> None:
        if not local_path:
            return
        path = Path(local_path)
        # Delete only while the path still belongs to the removed record;
        # a re-imported same-name doc points its new record at a new path
        doc = self._store.get(did)
        if doc is not None and doc.get("local_path") == local_path:
            return
        try:
            # Disk deletion off the event loop: syncing rmtree on large
            # directories would stall the worker's loop
            def _remove() -> None:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)

            await asyncio.to_thread(_remove)
        except (OSError, PermissionError):
            # Skip on file-in-use style errors; with the record gone the
            # path is unreferenced and can be overwritten/re-parsed later
            pass

    async def _run_one(self, did: str) -> None:
        doc = self._store.get(did)
        if doc is None:
            return
        await self._emit(DomainEvent.TASK_PROGRESS, did, kind="doc", progress=0.1, stage="parse")
        loop = asyncio.get_running_loop()
        try:
            # Extraction is CPU/IO intensive: run it in the pool so the
            # event loop stays responsive
            sections = await loop.run_in_executor(
                None, self._parse, Path(doc["local_path"]), doc["ext"]
            )
            payload = [
                {
                    "section_no": s.section_no,
                    "title": s.title,
                    "page_start": s.page_start,
                    "page_end": s.page_end,
                    "text": s.text,
                }
                for s in sections
            ]
            self._store.replace_sections(did, payload)
            self._store.set_status(did, "ready")
            for i, s in enumerate(sections):
                await self._emit(
                    DomainEvent.TASK_PROGRESS,
                    did,
                    kind="doc",
                    progress=(i + 1) / len(sections),
                    stage="parse",
                )
            await self._emit(
                DomainEvent.SOURCE_READY,
                did,
                kind="doc",
                title=doc["title"],
                sections=len(sections),
            )
        except ExtractError as exc:
            self._store.set_status(did, "failed", error=str(exc)[:500])
            await self._emit(DomainEvent.TASK_FAILED, did, kind="doc", error=str(exc)[:300])
        except Exception as exc:  # noqa: BLE001  # persist failure, never kill the worker
            self._store.set_status(did, "failed", error=f"Parse error: {exc}"[:500])
            await self._emit(
                DomainEvent.TASK_FAILED, did, kind="doc", error=f"Parse error: {exc}"[:300]
            )

    async def _emit(self, type_: str, did: str, **payload) -> None:
        if self._bus is not None:
            await self._bus.publish(
                Event(type=type_, actor=_ACTOR, payload={"source_id": did, **payload})
            )
