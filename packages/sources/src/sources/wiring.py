"""Wiring for sources: the single assembly point for standalone
runs (rest.py) and the aggregate deployment.

Submodules (repo/doc/web) stay decoupled, each with its own store and
queue; this module only composes them. clone_fn / parse_fn are optional
hooks for standalone tests and host wire_extras — they are not shared
facilities and must not appear on the module card's needs list.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from platform_capability import Wiring
from platform_eventbus import EventBus
from platform_secrets import SecretStore
from platform_settings import SettingsStore

from .capabilities import SourcesDeps, init_all, registry
from .files import build_files_router
from .modules.doc.store import DocStore
from .modules.doc.worker import DocWorker
from .modules.repo.store import RepoStore
from .modules.repo.worker import RepoWorker
from .modules.web.store import WebStore
from .settings import DEFS


def wire(
    data_dir: str | Path,
    *,
    workspace: str | Path,
    bus: EventBus | None = None,
    secrets: SecretStore | None = None,
    clone_fn=None,
    parse_fn=None,
    settings_store: SettingsStore | None = None,
) -> Wiring:
    from .migration import migrate_legacy_books_news

    data_dir = Path(data_dir)
    if settings_store is not None:
        settings_store.register_fresh(DEFS)
    migrate_legacy_books_news(data_dir)
    repo_store = RepoStore(data_dir / "repo.db")
    doc_store = DocStore(data_dir / "doc.db")
    web_store = WebStore(data_dir / "web.db")
    owns_secrets = secrets is None
    secrets = secrets or SecretStore(data_dir / "secrets.db")
    repo_queue: asyncio.Queue = asyncio.Queue()
    doc_queue: asyncio.Queue = asyncio.Queue()
    init_all(
        SourcesDeps(
            repo_store=repo_store,
            doc_store=doc_store,
            web_store=web_store,
            secrets=secrets,
            bus=bus,
            repo_queue=repo_queue,
            doc_queue=doc_queue,
            workspace=Path(workspace),
            settings=settings_store,
        )
    )
    repo_worker = RepoWorker(repo_store, bus, repo_queue, Path(workspace), clone_fn=clone_fn)
    doc_worker = DocWorker(doc_store, bus, doc_queue, Path(workspace), parse_fn=parse_fn)

    async def start() -> None:
        await asyncio.gather(repo_worker.start(), doc_worker.start())

    async def stop() -> None:
        await asyncio.gather(repo_worker.stop(), doc_worker.stop())

    def close() -> None:
        repo_store.close()
        doc_store.close()
        web_store.close()
        if owns_secrets:
            secrets.close()

    return Wiring(
        registry=registry,
        probe=lambda: {"status": "up"},
        start=start,
        stop=stop,
        close=close,
        # Read-only doc-file router: wire builds the doc_store locally and
        # hands it over; the deployment root never reads STORES
        extra_router=build_files_router(doc_store),
    )
