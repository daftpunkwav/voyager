"""Wiring for the browser service, shared by standalone and
aggregate deployment.
"""

from __future__ import annotations

from pathlib import Path

from platform_capability import Wiring
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .capabilities import DEFS, Deps, init_deps, registry
from .store import BrowserStore


def wire(
    data_dir: str | Path,
    *,
    workspace: str | Path,
    bus: EventBus | None = None,
    settings_store: SettingsStore | None = None,
) -> Wiring:
    data_dir = Path(data_dir)
    workspace = Path(workspace)
    owns_settings = settings_store is None
    settings_store = settings_store or SettingsStore(data_dir / "settings.db", bus)
    settings_store.register_fresh(DEFS)
    store = BrowserStore(data_dir / "browser.db")
    init_deps(Deps(store=store, settings=settings_store, bus=bus, workspace=workspace))

    def close() -> None:
        store.close()
        if owns_settings:
            settings_store.close()

    return Wiring(registry=registry, probe=lambda: {"status": "up"}, close=close)
