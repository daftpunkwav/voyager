"""Gateway upload endpoint tests: multipart landing, invalid requests, and
integration with a domain capability.

Uploads only transport data (multipart -> workspace/imports/); business
validation lives in the domain capability layer (add_document is used
here to verify the returned file_path closes the loop).
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gateway.uploads import build_upload_router


@pytest.fixture()
def client(tmp_path):
    app = FastAPI()
    app.include_router(build_upload_router(tmp_path / "ws"))
    return TestClient(app), tmp_path / "ws"


class TestUpload:
    def test_upload_saves_to_imports(self, client) -> None:
        tc, ws = client
        resp = tc.post(
            "/api/uploads", files={"file": ("报告.pdf", b"%PDF fake", "application/pdf")}
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["filename"] == "报告.pdf"
        assert body["size"] == len(b"%PDF fake")
        # lands under workspace/imports/<month>/ with a uuid prefix against
        # filename collisions
        assert "imports" in Path(body["file_path"]).parts
        assert Path(body["file_path"]).parent.parent == ws / "imports"
        assert "__" in Path(body["file_path"]).name
        assert Path(body["file_path"]).is_file()

    def test_upload_rejects_non_multipart(self, client) -> None:
        tc, _ = client
        resp = tc.post("/api/uploads", json={"file": "x"})
        assert resp.status_code == 400

    def test_upload_rejects_missing_file(self, client) -> None:
        tc, _ = client
        resp = tc.post("/api/uploads", files={"other": ("a.txt", b"x")})
        assert resp.status_code == 400

    def test_upload_rejects_empty(self, client) -> None:
        tc, _ = client
        resp = tc.post("/api/uploads", files={"file": ("a.txt", b"")})
        assert resp.status_code == 400

    def test_unsafe_filename_sanitized(self, client) -> None:
        tc, ws = client
        resp = tc.post("/api/uploads", files={"file": ("../../evil name.txt", b"x")})
        assert resp.status_code == 201
        path = Path(resp.json()["file_path"])
        assert path.parent.parent == ws / "imports"  # no path escape
        assert ".." not in path.name
