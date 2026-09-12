"""Overview page aggregation contract smoke test: after build(), all six data
sources are fetchable (/health, activity feed, usage, index jobs, sources, notes). The
overview page adds no new endpoints -- this test pins the existing endpoints it depends
on so they are not broken.
"""

from agent.llm import FakeLLM
from fastapi.testclient import TestClient
from host.assemble import build

SOURCES = [
    ("GET", "/health", None),
    ("GET", "/api/activity/feed?limit=10", None),
    ("POST", "/api/llm/capabilities/get_usage_stats", {"days": 7}),
    ("POST", "/api/graph/capabilities/list_index_jobs", {}),
    ("POST", "/api/sources/capabilities/list_repos", {}),
    ("POST", "/api/notes/capabilities/list_notes", {"limit": 500}),
]


def test_overview_contract_smoke(tmp_path) -> None:
    app = build(tmp_path / "data", tmp_path / "ws", llm=FakeLLM(default="ok"))
    with TestClient(app) as client:
        # Create some data (a note plus one user message) so the cards have
        # content to render
        client.post("/api/notes/capabilities/create_note", json={"title": "overview smoke"})
        client.post("/api/chat/messages", json={"content": "ok"})

        for method, url, body in SOURCES:
            if method == "GET":
                resp = client.get(url)
            else:
                resp = client.post(url, json=body)
            assert resp.status_code == 200, f"{url} -> {resp.status_code}: {resp.text[:200]}"

        # Key field shapes of each data source (cards depend on them for rendering)
        health = client.get("/health").json()
        assert "services" in health
        feed = client.get("/api/activity/feed?limit=10").json()["events"]
        assert any(e["type"] == "note.created" for e in feed)
        usage = client.post("/api/llm/capabilities/get_usage_stats", json={"days": 7}).json()[
            "result"
        ]
        assert {"input_tokens", "output_tokens", "calls", "by_model"} <= set(usage)
        notes = client.post("/api/notes/capabilities/list_notes", json={"limit": 500}).json()[
            "result"
        ]
        assert any(n["title"] == "overview smoke" for n in notes)
