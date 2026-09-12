"""Page-awareness integration: report_page_context lands in the agent's
PageContextRegistry and the master context assembly includes the summary (the agent uses
it to answer "what the user is looking at").
"""

from agent.llm import FakeLLM
from fastapi.testclient import TestClient
from host.assemble import build


def test_page_context_reaches_agent(tmp_path) -> None:
    app = build(tmp_path / "data", tmp_path / "ws", llm=FakeLLM(default="ok"))
    with TestClient(app) as client:
        out = client.post(
            "/api/agent/capabilities/report_page_context",
            json={
                "page": "notes",
                "summary": '36 notes, currently viewing "langgraph notes"',
                "counts": {"notes": 36},
                "selected": "langgraph notes",
            },
        ).json()["result"]
        assert out == {"page": "notes", "ok": True}

        # Registry read-back: current points at the page, the rendered summary
        # includes counts and the selection
        agent_app = app.state.backend.agent
        pages = agent_app.pages
        assert pages.current() is not None
        assert pages.current().page == "notes"
        rendered = pages.render()
        assert "36 notes" in rendered
        assert "notes=36" in rendered
        assert "当前选中: langgraph notes" in rendered

        # Context assembly: the builder output contains the "user's current page" layer
        system = agent_app.master._spawner._build_system(None, "orchestrator")  # Backend handle
        assert "用户当前页面" in system and "36 notes" in system


def test_activity_report_event_chain(tmp_path) -> None:
    """Activity reports -> user.activity events enter the event log (agent-side
    observation is removed; the frontend toggle only controls whether reports
    are sent)."""
    app = build(tmp_path / "data2", tmp_path / "ws2", llm=FakeLLM(default="ok"))
    backend = app.state.backend
    with TestClient(app) as client:
        resp = client.post(
            "/api/activity",
            json={
                "kind": "page_view",
                "page": "/notes",
                "detail": {},
            },
        )
        assert resp.status_code == 200 and resp.json()["seq"] > 0
        events = [e for _, e in backend.log.read_after(types=["user.activity"])]
        assert events and events[-1].payload["page"] == "/notes"
