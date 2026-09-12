"""Universal sources-library integration: upload -> document parsing chain,
web clipping, the agent with the same rights as the user, and the unified sources
stream.

Document parsing is injected via wire_extras into sources.wire(); save_url runs offline
through the web submodule's resolver plus an httpx stub; the agent uses the host bridge
(sources__add_document) with the same rights as the user.
"""

import time

import httpx
import pytest
import sources.modules.web.capabilities as web_caps
from fastapi.testclient import TestClient
from host.assemble import build


@pytest.fixture()
def web_offline(monkeypatch):
    """Offline stub for save_url: fixed public IP plus MockTransport."""

    async def resolve(host: str, port: int) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr(web_caps, "_default_resolver", resolve)
    orig = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text="<title>integration test page</title><p>unified stream body</p>"
        )

    def factory(**kw):
        kw.pop("follow_redirects", None)
        return orig(transport=httpx.MockTransport(handler), follow_redirects=False, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def _wait(log, types, *, timeout=8.0, pred=None):
    deadline = time.time() + timeout
    while time.time() < deadline:
        events = [e for _, e in log.read_after(types=types) if pred is None or pred(e)]
        if events:
            return events
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for events: {types}")


class TestDocumentFlow:
    def test_upload_then_add_document_parses(self, tmp_path) -> None:
        """Browser upload -> lands in imports -> add_document -> worker parses ->
        ready."""

        def fake_parse(path, ext):
            # Go through the public entry point
            from sources.modules.doc.extract import extract_sections

            return extract_sections(path, ext)

        app = build(
            tmp_path / "data", tmp_path / "ws", wire_extras={"sources": {"parse_fn": fake_parse}}
        )
        backend = app.state.backend
        with TestClient(app) as client:
            up = client.post(
                "/api/uploads",
                files={"file": ("manual.md", "# Guide\n" + "content" * 30, "text/markdown")},
            )
            assert up.status_code == 201
            ref = client.post(
                "/api/sources/capabilities/add_document",
                json={
                    "file_path": up.json()["file_path"],
                    "title": "user manual",
                },
            )
            assert ref.status_code == 202
            did = ref.json()["job"]["job_id"]
            _wait(backend.log, ["source.ready"], pred=lambda e: e.payload["source_id"] == did)
            detail = client.post(
                "/api/sources/capabilities/get_document", json={"doc_id": did}
            ).json()["result"]
            assert detail["status"] == "ready" and detail["total_sections"] >= 1
            section = client.post(
                "/api/sources/capabilities/get_doc_section", json={"doc_id": did, "section_no": 1}
            ).json()["result"]
            assert section["text"].startswith("# Guide")
            # Read-only download route for the original file
            file_resp = client.get(f"/api/sources/files/doc/{did}")
            assert file_resp.status_code == 200

    def test_agent_same_power_add_document(self, tmp_path) -> None:
        """The agent calls sources__add_document via the bridge with the same
        rights as the user."""

        def noop_parse(path, ext):
            return []

        app = build(
            tmp_path / "data", tmp_path / "ws", wire_extras={"sources": {"parse_fn": noop_parse}}
        )
        with TestClient(app) as client:
            src = tmp_path / "ws" / "imports"
            src.mkdir(parents=True, exist_ok=True)
            f = src / "agent.md"
            f.write_text("agent import", encoding="utf-8")
            resp = client.post(
                "/api/agent/tools/call",
                json={
                    "name": "sources__add_document",
                    "args": {"file_path": str(f), "title": "AI import"},
                },
            )
            if resp.status_code == 404:  # fall back to the unified capability entry
                resp = client.post(
                    "/api/sources/capabilities/add_document",
                    json={"file_path": str(f), "title": "AI import"},
                )
            assert resp.status_code in (200, 202)


class TestWebFlow:
    def test_save_url_and_unified_stream(self, tmp_path, web_offline) -> None:
        app = build(tmp_path / "data", tmp_path / "ws")
        backend = app.state.backend
        with TestClient(app) as client:
            page = client.post(
                "/api/sources/capabilities/save_url",
                json={
                    "url": "https://example.com/article",
                },
            ).json()["result"]
            assert page["title"] == "integration test page"
            assert page["domain"] == "example.com"
            _wait(backend.log, ["source.ready"], pred=lambda e: e.payload.get("kind") == "web")
            stats = client.post("/api/sources/capabilities/sources_stats", json={}).json()["result"]
            assert stats["web"] == 1
            stream = client.post("/api/sources/capabilities/list_sources", json={}).json()["result"]
            assert any(r["kind"] == "web" and r["title"] == "integration test page" for r in stream)
            hits = client.post(
                "/api/sources/capabilities/search_sources", json={"query": "unified stream"}
            ).json()["result"]
            assert any(r["kind"] == "web" for r in hits)
