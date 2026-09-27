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
from gateway.mounts import MountSpec
from gateway.ratelimit import RateLimiter
from gateway.uploads import build_upload_router


@pytest.fixture()
def client(tmp_path):
    app = FastAPI()
    app.include_router(build_upload_router(tmp_path / "ws", RateLimiter(600, 8)))
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

    def test_oversize_content_length_rejected_before_spool(self, client) -> None:
        """An honest oversized Content-Length is refused up front (413)
        without the multipart parser spooling the body to disk first; the
        streamed cap stays as the fallback for lying headers."""
        tc, _ = client
        resp = tc.post(
            "/api/uploads",
            files={"file": ("big.bin", b"x")},
            headers={"content-length": str(1024 * 1024 * 1024 + 1)},
        )
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "GATEWAY.PAYLOAD_TOO_LARGE"

    def test_lying_content_length_hits_the_streamed_cap(self, client, monkeypatch) -> None:
        """A small (lying) Content-Length passes the pre-check: the streamed
        cap is the fallback. The partial spool file must not survive on disk."""
        import gateway.uploads as uploads_mod

        monkeypatch.setattr(uploads_mod, "_MAX_BYTES", 8)
        tc, ws = client
        # content-length overridden below the cap: only the streamed cap can stop this body
        resp = tc.post(
            "/api/uploads",
            files={"file": ("big.bin", b"x" * 100)},
            headers={"content-length": "4"},
        )
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "GATEWAY.PAYLOAD_TOO_LARGE"
        leftovers = [f for d in (ws / "imports").iterdir() for f in d.iterdir()]
        assert leftovers == []  # the partial body is unlinked

    def test_garbage_content_length_is_tolerated(self, client) -> None:
        """An unparseable Content-Length must not crash the endpoint: the
        ValueError is swallowed and the streamed cap remains the only limit."""
        tc, _ = client
        resp = tc.post(
            "/api/uploads",
            files={"file": ("a.txt", b"hello")},
            headers={"content-length": "not-a-number"},
        )
        assert resp.status_code == 201
        assert resp.json()["size"] == 5


class TestUploadRateLimit:
    def test_rate_limited_before_body_is_read(self, tmp_path, echo_registry) -> None:
        """Exhausting the limiter returns 429 through the unified envelope
        and must not leave anything on disk: the check runs before the body
        is read or spooled."""
        from gateway.rest import create_app

        app = create_app(
            [MountSpec(domain="echo", registry=echo_registry)],
            db_path=tmp_path / "gw.db",
            rate_limit_per_minute=2,
            uploads_workspace=tmp_path / "ws",
        )
        imports = tmp_path / "ws" / "imports"
        with TestClient(app) as tc:
            assert tc.post("/api/uploads", files={"file": ("a.txt", b"1")}).status_code == 201
            assert tc.post("/api/uploads", files={"file": ("b.txt", b"2")}).status_code == 201
            before = sorted(p.name for p in imports.rglob("*") if p.is_file())
            r = tc.post("/api/uploads", files={"file": ("c.txt", b"3")})
            assert r.status_code == 429
            assert r.json()["error"]["code"] == "GATEWAY.RATE_LIMITED"
        after = sorted(p.name for p in imports.rglob("*") if p.is_file())
        assert after == before  # the throttled upload never touched the disk
