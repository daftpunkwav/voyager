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
from platform_contracts import DomainEvent, ServiceError


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
                # An over-long marker exercises the endpoint's 64-char cap.
                resp = client.post(
                    "/api/workspace/switch", json={"dir": str(new_ws), "marker": "m" * 100}
                )
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

                # The switch is announced for other tabs/sessions; the marker
                # echoes back so the initiating tab can recognize its own
                # broadcast. A client-supplied marker is capped at 64 chars.
                switched = [
                    e.payload
                    for _, e in app.state.backend.log.read_after(
                        types=[DomainEvent.WORKSPACE_SWITCHED]
                    )
                ]
                assert switched and switched[-1]["workspace"] == str(new_ws)
                assert switched[-1]["marker"] == "m" * 64

                # A second switch works: the switch endpoint re-mounts itself
                # with every generation instead of stranding the old routes.
                resp2 = client.post("/api/workspace/switch", json={"dir": str(back_ws)})
                assert resp2.status_code == 200, resp2.text
                listing2 = client.get("/api/workspace/list", params={"path": ""}).json()
                assert "hello.txt" not in [e["name"] for e in listing2["entries"]]
                # An omitted marker stays a (empty) payload field, so the
                # echo contract holds for marker-less clients too.
                switched2 = [
                    e.payload
                    for _, e in app.state.backend.log.read_after(
                        types=[DomainEvent.WORKSPACE_SWITCHED]
                    )
                ]
                assert switched2[-1]["marker"] == ""
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

    def test_switch_same_target_is_noop(self, tmp_path) -> None:
        import os

        ws = ROOT / "data" / f".test-ws-same-{os.getpid()}"
        ws.mkdir(parents=True, exist_ok=True)
        try:
            app = build(tmp_path / "data", ws)
            with TestClient(app) as client:
                before = app.state.backend.agent
                resp = client.post("/api/workspace/switch", json={"dir": str(ws)})
                assert resp.status_code == 200, resp.text
                assert "nothing was rebuilt" in resp.json()["note"]
                assert app.state.backend.agent is before
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_switch_failure_rolls_back(self, tmp_path) -> None:
        import os

        ws = ROOT / "data" / f".test-ws-rb-{os.getpid()}"
        ws.mkdir(parents=True, exist_ok=True)
        try:
            app = build(tmp_path / "data", ws)
            with TestClient(app) as client:
                rb = app.state.agent_rebuilder
                orig = rb.build_fn
                calls: list = []

                def flaky(target):
                    calls.append(target)
                    if len(calls) == 1:
                        raise RuntimeError("boom")
                    return orig(target)

                rb.build_fn = flaky  # type: ignore[method-assign]
                other = ROOT / "data" / f".test-ws-rb-new-{os.getpid()}"
                resp = client.post("/api/workspace/switch", json={"dir": str(other)})
                assert resp.status_code == 503, resp.text
                assert "rolled back" in resp.json()["error"]["message"]
                # Rolled back to a live generation on the old workspace.
                assert rb.agent is not None
                assert rb.current_workspace == ws
                assert client.get("/health").status_code == 200
                # The setting still points at the old workspace.
                assert app.state.backend.settings_store.get("agent.workspace.dir") != str(other)
        finally:
            shutil.rmtree(ws, ignore_errors=True)
            shutil.rmtree(ROOT / "data" / f".test-ws-rb-new-{os.getpid()}", ignore_errors=True)

    def test_switch_total_failure_marks_not_running(self, tmp_path) -> None:
        import os

        ws = ROOT / "data" / f".test-ws-dead-{os.getpid()}"
        ws.mkdir(parents=True, exist_ok=True)
        try:
            app = build(tmp_path / "data", ws)
            with TestClient(app) as client:
                rb = app.state.agent_rebuilder

                def always_fail(target):
                    raise RuntimeError("boom")

                rb.build_fn = always_fail  # type: ignore[method-assign]
                other = ROOT / "data" / f".test-ws-dead-new-{os.getpid()}"
                resp = client.post("/api/workspace/switch", json={"dir": str(other)})
                assert resp.status_code == 503, resp.text
                assert rb.agent is None
                # A later switch reports the honest state instead of tearing
                # down a half-closed generation again.
                resp2 = client.post("/api/workspace/switch", json={"dir": str(other)})
                assert resp2.status_code == 503
                assert "not running" in resp2.json()["error"]["message"]
        finally:
            shutil.rmtree(ws, ignore_errors=True)
            shutil.rmtree(ROOT / "data" / f".test-ws-dead-new-{os.getpid()}", ignore_errors=True)

    def test_switch_without_rebuilder_is_unavailable(self) -> None:
        app = FastAPI()

        @app.exception_handler(ServiceError)
        async def _service_error(_request, exc: ServiceError) -> JSONResponse:
            return JSONResponse(status_code=exc.http_status, content=exc.to_envelope())

        app.include_router(build_switch_router())
        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.post("/api/workspace/switch", json={"dir": "/tmp/x"}).status_code == 503
