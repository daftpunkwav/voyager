"""Tests for the browser service: capabilities, REST, and service.json
consistency.
"""

import json
from pathlib import Path

import pytest
from browser.capabilities import registry
from browser.rest import create_app
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER
from platform_eventbus import EventBus, EventLog
from platform_settings import SettingsStore

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

USER_CTX = ActorContext(actor=LOCAL_USER)
SERVICE_DIR = Path(__file__).parent.parent


@pytest.fixture()
def deps(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    settings_store = SettingsStore(tmp_path / "settings.db", bus)
    application = create_app(tmp_path, workspace=workspace, bus=bus, settings_store=settings_store)
    application.state.settings_store = settings_store
    application.state.event_log = log
    yield application
    log.close()
    settings_store.close()


class TestCapabilities:
    async def test_navigate(self, deps) -> None:
        result = await execute(registry, "navigate", USER_CTX, {"url": "https://example.com"})
        assert result["ok"] is True

    async def test_domain_block(self, deps) -> None:
        settings_store = deps.state.settings_store
        await settings_store.set("browser.allowed_domains", ["github.com"], actor=USER_CTX.actor)
        with pytest.raises(Exception) as exc:
            await execute(registry, "navigate", USER_CTX, {"url": "https://example.com"})
        assert "FORBIDDEN" in str(exc.value) or "not in allowlist" in str(exc.value)


class TestRest:
    def test_health(self, deps) -> None:
        with TestClient(deps) as client:
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_service_json_matches_registry(self) -> None:
        card = json.loads((SERVICE_DIR / "service.json").read_text(encoding="utf-8"))
        assert sorted(card["capabilities"]) == registry.names()
