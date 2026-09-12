"""Inject the settings domain dependencies for the capability tests."""

import pytest
from platform_eventbus import EventBus, EventLog
from platform_settings import SettingsStore
from settings import capabilities
from settings.capabilities import Deps
from settings.settings import DEFS


@pytest.fixture()
async def deps(tmp_path):
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    store = SettingsStore(tmp_path / "settings.db", bus)
    store.register(DEFS)
    capabilities.init_deps(Deps(store=store))
    yield store, log
    store.close()
