"""Restartless workspace rebuild: candidate validation and the switch endpoint.

The switch path is exercised end-to-end with TestClient (lifespan runs, so
loop/MCP tasks are live): switch, invalid input, and a missing rebuilder.
"""

import shutil

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from host.agent_rebuild import build_switch_router, resolve_candidate_dir
from host.assemble import ROOT, build
from platform_contracts import ServiceError


class TestResolveCandidate:
    def test_relative_joins_root(self) -> None:
        assert resolve_candidate_dir("my/workspace", ROOT) == ROOT / "my" / "workspace"

    def test_absolute_inside_root_passes(self) -> None:
        target = ROOT / "data" / "ws2"
        assert resolve_candidate_dir(str(target), ROOT) == target

    def test_empty_rejected(self) -> None:
        with pytest.raises(ServiceError, match="must not be empty"):
            resolve_candidate_dir("   ", ROOT)

    def test_parent_segments_rejected(self) -> None:
        with pytest.raises(ServiceError, match="must not contain"):
            resolve_candidate_dir("../outside", ROOT)

    def test_absolute_outside_root_rejected(self, tmp_path) -> None:
        with pytest.raises(ServiceError, match="inside the repo root"):
            resolve_candidate_dir(str(tmp_path / "ws"), ROOT)


class TestSwitchEndpoint:
    def test_switch_moves_workspace_without_restart(self, tmp_path) -> None:
        import os

        # Switch targets must stay inside the repo root (same rule as
        # assembly); use a self-cleaning directory under data/.
        new_ws = ROOT / "data" / f".test-ws-switch-{os.getpid()}"
        back_ws = ROOT / "data" / f".test-ws-back-{os.getpid()}"
        new_ws.mkdir(parents=True, exist_ok=True)
        try:
            (new_ws / "hello.txt").write_text("new root", encoding="utf-8")
            app = build(tmp_path / "data", tmp_path / "ws-old")
            with TestClient(app) as client:
                resp = client.post("/api/workspace/switch", json={"dir": str(new_ws)})
                assert resp.status_code == 200, resp.text
                assert resp.json()["workspace"] == str(new_ws)

                # The setting is persisted by the endpoint itself.
                assert app.state.backend.settings_store.get("agent.workspace.dir") == str(new_ws)

                # The workspace browser now serves the new root.
                listing = client.get("/api/workspace/list", params={"path": ""}).json()
                assert "hello.txt" in [e["name"] for e in listing["entries"]]

                # The agent generation was replaced and still answers.
                assert app.state.backend.agent is app.state.agent_rebuilder.agent
                assert client.get("/health").status_code == 200

                # A second switch works: the switch endpoint re-mounts itself
                # with every generation instead of stranding the old routes.
                resp2 = client.post("/api/workspace/switch", json={"dir": str(back_ws)})
                assert resp2.status_code == 200, resp2.text
                listing2 = client.get("/api/workspace/list", params={"path": ""}).json()
                assert "hello.txt" not in [e["name"] for e in listing2["entries"]]
        finally:
            shutil.rmtree(new_ws, ignore_errors=True)
            shutil.rmtree(back_ws, ignore_errors=True)

    def test_switch_rejects_bad_input(self, tmp_path) -> None:
        app = build(tmp_path / "data", tmp_path / "ws")
        with TestClient(app) as client:
            assert (
                client.post("/api/workspace/switch", json={"dir": "../outside"}).status_code == 400
            )
            assert client.post("/api/workspace/switch", json={}).status_code == 400

    def test_switch_without_rebuilder_is_unavailable(self) -> None:
        app = FastAPI()

        @app.exception_handler(ServiceError)
        async def _service_error(_request, exc: ServiceError) -> JSONResponse:
            return JSONResponse(status_code=exc.http_status, content=exc.to_envelope())

        app.include_router(build_switch_router())
        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.post("/api/workspace/switch", json={"dir": "/tmp/x"}).status_code == 503
