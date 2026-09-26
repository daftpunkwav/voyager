"""Origin/Host guard tests: the local REST surface must refuse requests whose
Host names another machine (DNS rebinding — a rebound attacker domain still
carries its own name in Host) and browser requests whose Origin is not the
app's own loopback origin (cross-origin CSRF against the write endpoints).

Non-browser clients (curl / local scripts) send no Origin and keep working;
the vite dev server origin (:5173) passes because only the hostname is
judged, never the port.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def tc(app):
    with TestClient(app) as client:
        yield client


class TestHostGuard:
    def test_loopback_ip_host_passes(self, tc) -> None:
        r = tc.get("/health", headers={"Host": "127.0.0.1:8000"})
        assert r.status_code == 200

    def test_localhost_name_passes(self, tc) -> None:
        r = tc.get("/health", headers={"Host": "localhost:8000"})
        assert r.status_code == 200

    def test_ipv6_loopback_host_passes(self, tc) -> None:
        assert tc.get("/health", headers={"Host": "[::1]:8000"}).status_code == 200

    def test_lan_ip_host_passes(self, tc) -> None:
        """A private-range IP literal host keeps working (Bearer-token LAN
        use); the guard only rejects DNS names."""
        r = tc.get("/health", headers={"Host": "10.0.0.8:8000"})
        assert r.status_code == 200

    def test_attacker_dns_name_host_is_403(self, tc) -> None:
        """DNS rebinding: evil.com resolves to 127.0.0.1 but presents its own
        name in Host — the request must be refused before any handler runs."""
        r = tc.get("/health", headers={"Host": "evil.com:8000"})
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "GATEWAY.FORBIDDEN"

    def test_rebound_write_endpoint_is_403(self, tc) -> None:
        """The same refusal covers write endpoints: a rebound page cannot
        drive POST /api/chat/messages under its own hostname."""
        r = tc.post(
            "/api/chat/messages",
            content=b'{"content": "hi"}',
            headers={"Host": "evil.com", "Content-Type": "application/json"},
        )
        assert r.status_code == 403

    def test_missing_host_is_403(self, tc) -> None:
        r = tc.get("/health", headers={"Host": ""})
        assert r.status_code == 403

    def test_mismatched_suffix_name_is_403(self, tc) -> None:
        """A name that merely ends in a trusted token is still a foreign
        domain (evilllc / 127.0.0.1.evil.com)."""
        assert tc.get("/health", headers={"Host": "localhost.evil.com"}).status_code == 403
        assert tc.get("/health", headers={"Host": "evillocalhost"}).status_code == 403


class TestOriginGuard:
    def test_same_origin_request_passes(self, tc) -> None:
        """Production same-origin (the UI served next to the API)."""
        r = tc.post(
            "/api/chat/messages",
            json={"content": "hi"},
            headers={"Origin": "http://127.0.0.1:8000"},
        )
        assert r.status_code == 200

    def test_vite_dev_origin_passes(self, tc) -> None:
        """The vite dev server proxies to the API with its own origin
        attached; only the hostname is judged, so :5173 passes."""
        r = tc.post(
            "/api/chat/messages",
            json={"content": "hi"},
            headers={"Origin": "http://127.0.0.1:5173"},
        )
        assert r.status_code == 200

    def test_cross_origin_post_is_403(self, tc) -> None:
        """CSRF: a page on evil.com can send a no-preflight POST with a JSON
        body as text/plain — the Origin header gives it away."""
        r = tc.post(
            "/api/chat/messages",
            content=b'{"content": "injected prompt"}',
            headers={"Origin": "http://evil.com", "Content-Type": "text/plain"},
        )
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "GATEWAY.FORBIDDEN"
        rows = tc.get("/api/chat/messages").json()["messages"]
        assert all(m["payload"]["content"] != "injected prompt" for m in rows)

    def test_null_origin_is_403(self, tc) -> None:
        """Sandboxed frames and file:// pages send `Origin: null`."""
        r = tc.post(
            "/api/chat/messages",
            json={"content": "hi"},
            headers={"Origin": "null"},
        )
        assert r.status_code == 403

    def test_no_origin_keeps_working(self, tc) -> None:
        """Non-browser clients (curl / local scripts) send no Origin."""
        r = tc.post("/api/chat/messages", json={"content": "hi"})
        assert r.status_code == 200

    def test_cross_origin_get_is_403(self, tc) -> None:
        """Cross-origin GETs carry Origin too (fetch/XHR); blocking them
        closes the read side a DNS-rebind would otherwise expose."""
        r = tc.get("/api/chat/messages", headers={"Origin": "https://evil.com"})
        assert r.status_code == 403

    def test_multipart_upload_from_foreign_origin_is_403(self, tc) -> None:
        """multipart/form-data is CORS-safelisted: without the guard a foreign
        page could land files via a no-preflight form/fetch POST."""
        r = tc.post(
            "/api/uploads",
            files={"file": ("a.txt", b"x")},
            headers={"Origin": "http://evil.com"},
        )
        assert r.status_code == 403
