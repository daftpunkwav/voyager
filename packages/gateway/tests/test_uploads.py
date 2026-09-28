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

    def test_lying_content_length_rejected_at_spool(self, client, monkeypatch) -> None:
        """A small (lying) Content-Length passes the pre-check: the receive
        boundary cap stops the body while Starlette is still spooling it, so
        no destination directory is even created."""
        import gateway.uploads as uploads_mod

        monkeypatch.setattr(uploads_mod, "_MAX_BYTES", 8)
        tc, ws = client
        # content-length overridden below the cap: only the receive cap can stop this body
        resp = tc.post(
            "/api/uploads",
            files={"file": ("big.bin", b"x" * 100)},
            headers={"content-length": "4"},
        )
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "GATEWAY.PAYLOAD_TOO_LARGE"
        assert not (ws / "imports").exists()  # rejected before any landing

    def test_chunked_oversize_rejected_without_content_length(self, client, monkeypatch) -> None:
        """A chunked body carries no Content-Length at all: the receive
        boundary cap is still enforced."""
        import gateway.uploads as uploads_mod

        monkeypatch.setattr(uploads_mod, "_MAX_BYTES", 8)
        tc, ws = client
        resp = tc.post(
            "/api/uploads",
            files={"file": ("big.bin", b"x" * 100)},
            headers={"Transfer-Encoding": "chunked"},
        )
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "GATEWAY.PAYLOAD_TOO_LARGE"
        assert not (ws / "imports").exists()

    def test_upload_above_spool_roll_size_still_succeeds(self, client) -> None:
        """A body large enough to roll Starlette's spooled form data to disk
        parses fine through the async-with form (spooled temp files are closed
        and removed by the context exit, never left for the caller)."""
        tc, _ = client
        body = b"y" * (2 * 1024 * 1024)
        resp = tc.post("/api/uploads", files={"file": ("big-ok.bin", body)})
        assert resp.status_code == 201
        assert resp.json()["size"] == len(body)
        assert Path(resp.json()["file_path"]).is_file()

    def test_extra_file_fields_rejected(self, client) -> None:
        """max_files=1 at the multipart parser: a second file field fails the
        parse with the unified 400 envelope (Starlette raises
        MultiPartException; the handler maps parse failures to
        GATEWAY.INVALID_INPUT)."""
        tc, ws = client
        resp = tc.post(
            "/api/uploads",
            files=[("file", ("a.txt", b"x")), ("extra", ("b.txt", b"y"))],
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "GATEWAY.INVALID_INPUT"
        imports = ws / "imports"
        assert not imports.exists() or list(imports.rglob("*")) == []

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


class TestUploadStall:
    async def test_stalled_body_times_out(self, tmp_path, monkeypatch) -> None:
        """A client that stops sending mid-body must not pin the connection
        (and Starlette's spool temp file) forever: the receive boundary
        carries an idle timeout and answers 408. Nothing lands on disk — the
        destination file is only created after a successful parse."""
        import asyncio

        import gateway.uploads as uploads_mod
        from fastapi import Request

        monkeypatch.setattr(uploads_mod, "_IDLE_TIMEOUT_S", 0.05)
        router = build_upload_router(tmp_path / "ws", RateLimiter(600, 8))
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/uploads",
            "query_string": b"",
            "headers": [(b"content-type", b"multipart/form-data; boundary=stalled")],
        }

        async def stall_receive():
            await asyncio.sleep(3600)

        request = Request(scope, receive=stall_receive)
        # The upload router's only route is the endpoint under test
        from fastapi.routing import APIRoute

        route = router.routes[0]
        assert isinstance(route, APIRoute)
        resp = await route.endpoint(request)
        assert resp.status_code == 408
        assert resp.body is not None and b"UPLOAD_TIMEOUT" in resp.body
        assert not (tmp_path / "ws" / "imports").exists()


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


class TestUploadSharesGatewayLimiter:
    def test_uploads_and_chat_share_one_limiter_instance(self, tmp_path, echo_registry) -> None:
        """/api/uploads joins the gateway-wide limiter (create_app stashes it
        on app.state for the hot-swap remount): exhausting chat requests must
        throttle uploads too, proving it is one instance, not two counters."""
        from gateway.rest import create_app

        app = create_app(
            [MountSpec(domain="echo", registry=echo_registry)],
            db_path=tmp_path / "gw.db",
            rate_limit_per_minute=3,
            uploads_workspace=tmp_path / "ws",
        )
        with TestClient(app) as tc:
            for i in range(3):
                assert tc.post("/api/chat/messages", json={"content": f"c{i}"}).status_code == 200
            r = tc.post("/api/uploads", files={"file": ("late.txt", b"x")})
            assert r.status_code == 429
            assert r.json()["error"]["code"] == "GATEWAY.RATE_LIMITED"
