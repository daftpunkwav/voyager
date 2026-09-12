"""Aggregated assembly tests: build() starts the whole system, /health reports
all six domains up, and capabilities are reachable through the aggregate entry point.
"""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from host.assemble import ROOT, _resolve_workspace, build
from platform_contracts import LOCAL_USER, ServiceError
from platform_settings import SettingsStore

DOMAINS = {"llm", "sources", "notes", "graph", "settings", "agent"}


def test_build_health_and_domain_call(tmp_path) -> None:
    app = build(tmp_path / "data", tmp_path / "ws")
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert DOMAINS <= set(body["services"])
        assert all(s["status"] == "up" for s in body["services"].values())

        # web -> gateway -> service chain: a domain capability call via the
        # aggregate entry point succeeds
        note = client.post(
            "/api/notes/capabilities/create_note", json={"title": "aggregate chain test"}
        )
        assert note.status_code == 200
        assert note.json()["result"]["title"] == "aggregate chain test"


def test_agent_settings_in_shared_store(tmp_path) -> None:
    app = build(tmp_path / "data", tmp_path / "ws")
    with TestClient(app) as client:
        items = client.post(
            "/api/settings/capabilities/get_settings", json={"module": "agent"}
        ).json()["result"]
        keys = {item["key"] for item in items}
        assert "agent.style" in keys
        # agent settings are registered into the shared store, so the settings
        # page can aggregate them


def test_domain_tools_reach_agent(tmp_path) -> None:
    app = build(tmp_path / "data", tmp_path / "ws")
    backend = app.state.backend
    names = backend.agent.spawner._toolbelt.names()
    assert "notes__create_note" in names  # domain capability injected into the agent tool set
    assert "llm__complete" in names


class TestWorkspaceResolution:
    """Workspace resolution: an explicit argument wins; otherwise
    agent.workspace.dir is read with relative paths joined onto the repo root;
    `..` segments and absolute paths leaving the repo root are rejected."""

    def _store(self, tmp_path, raw) -> SettingsStore:
        store = SettingsStore(tmp_path / "settings.db")
        from agent.settings import DEFS as AGENT_SETTING_DEFS

        store.register_fresh(AGENT_SETTING_DEFS)
        if raw is not None:
            asyncio.run(store.set("agent.workspace.dir", raw, LOCAL_USER))
        return store

    def test_explicit_dir_wins(self, tmp_path) -> None:
        store = self._store(tmp_path, "from_setting")
        assert _resolve_workspace(tmp_path / "explicit", store) == tmp_path / "explicit"

    def test_setting_relative_joins_root(self, tmp_path) -> None:
        store = self._store(tmp_path, "my/workspace")
        assert _resolve_workspace(None, store) == ROOT / "my" / "workspace"

    def test_empty_setting_falls_back_to_default(self, tmp_path) -> None:
        store = self._store(tmp_path, "")
        assert _resolve_workspace(None, store) == ROOT / "data" / "workspace"

    def test_dotdot_rejected(self, tmp_path) -> None:
        store = self._store(tmp_path, "../evil")
        with pytest.raises(ServiceError) as exc:
            _resolve_workspace(None, store)
        assert exc.value.body.code == "AGENT.INVALID_INPUT"

    def test_absolute_root_rejected(self, tmp_path) -> None:
        """Absolute drive roots (C:\\ or /) are rejected, not silently falling
        back to the default directory."""
        store = self._store(tmp_path, str(Path(ROOT.anchor)))
        with pytest.raises(ServiceError) as exc:
            _resolve_workspace(None, store)
        assert exc.value.body.code == "AGENT.INVALID_INPUT"

    def test_absolute_outside_root_rejected(self, tmp_path) -> None:
        """Same-drive paths outside the repo (D:\\evil) are rejected as well."""
        outside = Path(ROOT.anchor) / "evil-ws"
        store = self._store(tmp_path, str(outside))
        with pytest.raises(ServiceError) as exc:
            _resolve_workspace(None, store)
        assert exc.value.body.code == "AGENT.INVALID_INPUT"

    def test_absolute_inside_root_allowed(self, tmp_path) -> None:
        """Absolute paths under the repo root are allowed (no blanket ban on
        absolute paths)."""
        inside = ROOT / "in-repo-ws"
        store = self._store(tmp_path, str(inside))
        assert _resolve_workspace(None, store) == inside
