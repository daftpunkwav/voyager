"""Gateway workspace endpoint tests: containment, text detection, truncation,
and large-file streaming reads."""

import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gateway.workspace import _PREVIEW_MAX_BYTES, build_workspace_router


@pytest.fixture()
def client(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir(parents=True)
    (ws / "hello.txt").write_text("hello world\n", encoding="utf-8", newline="\n")
    (ws / "binary.dat").write_bytes(b"\x00\x01\x02\x03")
    big_dir = ws / "big"
    big_dir.mkdir()
    big_file = big_dir / "big.txt"
    # Slightly more than the preview cap so truncation fires
    big_file.write_text("a" * (_PREVIEW_MAX_BYTES + 1024), encoding="utf-8")
    app = FastAPI()
    app.include_router(build_workspace_router(ws))
    return TestClient(app), ws


class TestList:
    def test_list_root(self, client) -> None:
        tc, _ = client
        resp = tc.get("/api/workspace/list")
        assert resp.status_code == 200
        body = resp.json()
        names = {e["name"] for e in body["entries"]}
        assert "hello.txt" in names
        assert "binary.dat" in names
        assert "big" in names
        assert body["truncated"] is False

    def test_list_subdir(self, client) -> None:
        tc, _ = client
        resp = tc.get("/api/workspace/list", params={"path": "big"})
        assert resp.status_code == 200
        body = resp.json()
        assert [e["name"] for e in body["entries"]] == ["big.txt"]
        assert body["truncated"] is False

    def test_list_not_found(self, client) -> None:
        tc, _ = client
        resp = tc.get("/api/workspace/list", params={"path": "nope"})
        assert resp.status_code == 200
        assert resp.json()["error"]["code"] == "WORKSPACE.NOT_FOUND"

    def test_list_file_rejected(self, client) -> None:
        tc, _ = client
        resp = tc.get("/api/workspace/list", params={"path": "hello.txt"})
        assert resp.status_code == 200
        assert resp.json()["error"]["code"] == "GATEWAY.INVALID_INPUT"

    def test_containment_traversal_rejected(self, client) -> None:
        tc, _ = client
        resp = tc.get("/api/workspace/list", params={"path": ".."})
        assert resp.status_code == 200
        assert resp.json()["error"]["code"] == "WORKSPACE.NOT_FOUND"

    def test_containment_absolute_rejected(self, client) -> None:
        tc, _ = client
        resp = tc.get("/api/workspace/list", params={"path": "C:/Windows"})
        assert resp.status_code == 200
        assert resp.json()["error"]["code"] == "WORKSPACE.NOT_FOUND"


class TestRead:
    def test_read_text_file(self, client) -> None:
        tc, _ = client
        resp = tc.get("/api/workspace/read", params={"path": "hello.txt"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["lines"] == ["hello world"]
        assert body["truncated"] is False
        assert body["total_bytes"] == len("hello world\n")

    def test_read_binary_rejected(self, client) -> None:
        tc, _ = client
        resp = tc.get("/api/workspace/read", params={"path": "binary.dat"})
        assert resp.status_code == 200
        assert resp.json()["error"]["code"] == "WORKSPACE.NOT_TEXT"

    def test_read_big_file_truncated(self, client) -> None:
        tc, _ = client
        resp = tc.get("/api/workspace/read", params={"path": "big/big.txt"})
        assert resp.status_code == 200
        body = resp.json()
        # bytes are limited even though the file is bigger than the cap
        assert body["truncated"] is True
        assert body["total_bytes"] == _PREVIEW_MAX_BYTES + 1024
        assert len(body["lines"]) == 1
        assert len(body["lines"][0]) == _PREVIEW_MAX_BYTES

    def test_read_line_limit(self, client) -> None:
        tc, _ = client
        # ask for fewer lines than exist
        resp = tc.get("/api/workspace/read", params={"path": "hello.txt", "limit": 1})
        assert resp.status_code == 200
        body = resp.json()
        assert body["lines"] == ["hello world"]
        assert body["truncated"] is True

    def test_read_not_found(self, client) -> None:
        tc, _ = client
        resp = tc.get("/api/workspace/read", params={"path": "missing.txt"})
        assert resp.status_code == 200
        assert resp.json()["error"]["code"] == "WORKSPACE.NOT_FOUND"


class TestPick:
    @pytest.mark.skipif(sys.platform != "win32", reason="drive enumeration is Windows-only")
    def test_pick_root_lists_drives(self, client) -> None:
        tc, _ = client
        resp = tc.get("/api/workspace/pick")
        assert resp.status_code == 200
        body = resp.json()
        assert body["parent"] is None
        assert body["entries"]  # at least one drive exists on Windows
        assert body["truncated"] is False

    def test_pick_workspace_dir(self, client) -> None:
        tc, ws = client
        resp = tc.get("/api/workspace/pick", params={"path": str(ws)})
        assert resp.status_code == 200
        body = resp.json()
        assert body["path"] == str(ws)
        assert body["parent"] is not None
        names = {e["name"] for e in body["entries"]}
        assert "hello.txt" in names
