"""Assembly for the notes service: the single wiring source for standalone
(rest.py) and aggregated (packages/host/) runs.

Responsibilities:
- Build the NoteStore / AssetStore, inject Deps, and register capabilities
- Return the Wiring with the read-only assets router as extra_router and
  the trash retention loop as start/stop

In aggregated mode the assembly root passes in a shared SettingsStore, so
setting definitions are registered into that store for unified rendering on
the settings page. Standalone runs may omit it; definitions are then not
registered and service behavior is unaffected. Wiring.start/stop drive the
trash retention loop: one purge at startup, then every 24 hours. A
retention_days of 0 makes it a no-op (lazy in-process maintenance, no
dedicated worker).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from platform_capability import Wiring
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from . import assets
from .capabilities import Deps, init_deps, registry
from .settings import DEFS
from .store import NoteStore


class TrashPruner:
    """Background task enforcing the trash retention policy; backs Wiring.start/stop."""

    def __init__(
        self,
        store: NoteStore,
        settings_store: SettingsStore | None,
        purge_assets: Callable[[str], list[str]] | None = None,
    ) -> None:
        self._store = store
        self._settings = settings_store
        self._purge_assets = purge_assets
        self._task: asyncio.Task | None = None

    def _retention_days(self) -> int:
        if self._settings is None:
            return 30  # default policy when settings are not wired (standalone)
        try:
            return int(self._settings.get("notes.trash.retention_days") or 0)
        except (TypeError, ValueError):
            return 30

    async def _loop(self) -> None:
        await asyncio.sleep(5.0)  # yield to process startup
        while True:
            purged = self._store.purge_expired(self._retention_days())
            for nid in purged:
                # Wiring holds the asset purge directly; bound after capability
                # registration to avoid an import cycle.
                if self._purge_assets:
                    self._purge_assets(nid)
            await asyncio.sleep(24 * 3600)

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None


def wire(
    data_dir: str | Path,
    *,
    bus: EventBus | None = None,
    settings_store: SettingsStore | None = None,
    workspace: str | Path | None = None,
) -> Wiring:
    if settings_store is not None:
        settings_store.register_fresh(DEFS)
    history_keep = int(
        (settings_store.get("notes.history.per_note") if settings_store else 20) or 0
    )
    store = NoteStore(Path(data_dir) / "notes.db", history_keep=history_keep)
    workspace = Path(workspace) if workspace else Path(__file__).parents[4] / "data" / "workspace"
    asset_store = assets.AssetStore(Path(data_dir) / "assets.db")

    def _max_asset_mb() -> int:
        if settings_store is None:
            return 20
        try:
            return int(settings_store.get("notes.assets.max_mb") or 20)
        except (TypeError, ValueError):
            return 20

    assets.init_store(asset_store, workspace, max_file_mb=_max_asset_mb)
    assets.register(registry)
    purge_assets = assets.purge_of_note
    init_deps(
        Deps(
            store=store,
            bus=bus,
            settings=settings_store,
            purge_assets=purge_assets,
            workspace=workspace,
        )
    )
    pruner = TrashPruner(store, settings_store, purge_assets=purge_assets)

    def close() -> None:
        store.close()
        asset_store.close()

    return Wiring(
        registry=registry,
        probe=lambda: {"status": "up"},
        start=pruner.start,
        stop=pruner.stop,
        close=close,
        # Read-only asset routes: wire() has already initialized the store, so
        # the router is built and passed here; the assembly root stays domain-agnostic.
        extra_router=assets.build_assets_router(),
    )
