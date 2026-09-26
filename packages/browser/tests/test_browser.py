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


class TestCommandDispatch:
    """The five browser commands dispatch to the host adapter with session,
    settings and workspace plumbed through, and map BrowserResult onto the
    public result dict. The adapter is stubbed: the real browser runs in
    desktop/browser-host, not here."""

    @staticmethod
    def _result(**overrides):
        from browser.host import BrowserResult

        values: dict = {
            "ok": True,
            "url": "",
            "title": "",
            "text": "",
            "screenshot_path": "",
            "error": "",
        }
        values.update(overrides)
        return BrowserResult(**values)

    async def test_navigate_forwards_settings(self, deps, monkeypatch) -> None:
        from browser import capabilities

        await deps.state.settings_store.set(
            "browser.allowed_domains", ["example.com"], actor=USER_CTX.actor
        )
        seen: dict = {}

        async def fake_navigate(session_id, url, *, headless, allowed_domains):
            seen.update(
                session_id=session_id, url=url, headless=headless, allowed_domains=allowed_domains
            )
            return self._result(ok=True, url=url, title="T", text="body")

        monkeypatch.setattr(capabilities, "navigate", fake_navigate)
        result = await execute(registry, "navigate", USER_CTX, {"url": "https://example.com/x"})
        assert seen["url"] == "https://example.com/x"
        assert seen["headless"] is True and seen["allowed_domains"] == ["example.com"]
        assert result == {
            "ok": True,
            "url": "https://example.com/x",
            "title": "T",
            "text": "body",
            "screenshot_path": "",
            "error": "",
        }

    async def test_click_type_and_read_touch_session_and_map_result(
        self, deps, monkeypatch
    ) -> None:
        from browser import capabilities

        seen: list[str] = []

        async def fake_click(session_id, selector, *, allowed_domains):
            seen.append(f"click:{session_id}")
            return self._result(text=f"clicked {selector}")

        async def fake_type(session_id, selector, text, *, allowed_domains):
            seen.append(f"type:{session_id}")
            return self._result(text=f"typed into {selector}")

        async def fake_read(session_id, *, allowed_domains):
            seen.append(f"read:{session_id}")
            return self._result(title="P", text="page body")

        monkeypatch.setattr(capabilities, "click", fake_click)
        monkeypatch.setattr(capabilities, "type_text", fake_type)
        monkeypatch.setattr(capabilities, "read_page", fake_read)

        clicked = await execute(
            registry, "click", USER_CTX, {"session_id": "s1", "selector": "#btn"}
        )
        typed = await execute(
            registry, "type", USER_CTX, {"session_id": "s1", "selector": "#box", "text": "hi"}
        )
        page = await execute(registry, "read", USER_CTX, {"session_id": "s1"})

        assert clicked["text"] == "clicked #btn"
        assert typed["text"] == "typed into #box"
        assert page["title"] == "P" and page["text"] == "page body"
        assert seen == ["click:s1", "type:s1", "read:s1"]  # same session tracked

    async def test_screenshot_passes_workspace(self, deps, tmp_path, monkeypatch) -> None:
        from browser import capabilities

        seen: dict = {}

        async def fake_screenshot(session_id, *, allowed_domains, workspace_dir):
            seen["workspace_dir"] = workspace_dir
            return self._result(screenshot_path=f"{workspace_dir}/browser-screenshots/s9.png")

        monkeypatch.setattr(capabilities, "screenshot", fake_screenshot)
        result = await execute(registry, "screenshot", USER_CTX, {"session_id": "s9"})
        assert result["screenshot_path"].endswith("browser-screenshots/s9.png")
        assert seen["workspace_dir"] == str(tmp_path / "workspace")

    async def test_commands_before_wiring_fail_fast(self, monkeypatch, tmp_path) -> None:
        """Without init_deps there is no store or settings: the command fails
        fast instead of half-executing."""
        from browser import capabilities

        monkeypatch.setattr(capabilities, "_deps", None)
        with pytest.raises(RuntimeError, match="deps not injected"):
            await execute(registry, "navigate", USER_CTX, {"url": "https://example.com"})


class TestRest:
    def test_health(self, deps) -> None:
        with TestClient(deps) as client:
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_service_json_matches_registry(self) -> None:
        card = json.loads((SERVICE_DIR / "service.json").read_text(encoding="utf-8"))
        assert sorted(card["capabilities"]) == registry.names()
