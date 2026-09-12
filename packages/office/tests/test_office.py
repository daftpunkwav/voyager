"""Tests for the office aggregate service: doc/slides CRUD and service.json
consistency.
"""

import json
from pathlib import Path

import pytest
from office.capabilities import registry
from office.rest import create_app
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
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    settings_store = SettingsStore(tmp_path / "settings.db", bus)
    application = create_app(tmp_path, bus=bus, settings_store=settings_store)
    application.state.event_log = log
    yield application, log
    log.close()
    settings_store.close()


class TestRegistry:
    def test_service_json_matches_registry(self) -> None:
        card = json.loads((SERVICE_DIR / "service.json").read_text(encoding="utf-8"))
        assert sorted(card["capabilities"]) == registry.names()


class TestDoc:
    async def test_create_and_get_doc(self, deps) -> None:
        doc = await execute(registry, "create_doc", USER_CTX, {"title": "Hello"})
        assert doc["title"] == "Hello"
        assert doc["kind"] == "doc"
        got = await execute(registry, "get_doc", USER_CTX, {"doc_id": doc["id"]})
        assert got["id"] == doc["id"]

    async def test_insert_block(self, deps) -> None:
        doc = await execute(registry, "create_doc", USER_CTX, {"title": "Doc"})
        updated = await execute(
            registry,
            "insert_block",
            USER_CTX,
            {
                "doc_id": doc["id"],
                "index": 0,
                "block": {"type": "paragraph", "text": "Hi"},
            },
        )
        assert len(updated["blocks"]) == 1

    async def test_delete_doc_emits_event(self, deps) -> None:
        _, log = deps
        doc = await execute(registry, "create_doc", USER_CTX, {"title": "t"})
        await execute(registry, "delete_doc", USER_CTX, {"doc_id": doc["id"]})
        types = [e.type for _, e in log.read_after()]
        assert "doc.created" in types and "doc.deleted" in types  # mirrors note.deleted


class TestSlides:
    async def test_create_and_add_slide(self, deps) -> None:
        deck = await execute(registry, "create_deck", USER_CTX, {"title": "Deck"})
        assert deck["kind"] == "slides"
        updated = await execute(
            registry,
            "add_slide",
            USER_CTX,
            {
                "deck_id": deck["id"],
                "slide": {"title": "Slide 1"},
            },
        )
        assert len(updated["blocks"]) == 1

    async def test_delete_deck_emits_event(self, deps) -> None:
        _, log = deps
        deck = await execute(registry, "create_deck", USER_CTX, {"title": "D"})
        await execute(registry, "delete_deck", USER_CTX, {"deck_id": deck["id"]})
        assert "doc.deleted" in [e.type for _, e in log.read_after()]


class TestRest:
    def test_health(self, deps) -> None:
        app, _log = deps
        with TestClient(app) as client:
            resp = client.get("/health")
        assert resp.status_code == 200
