"""Template service tests: capability calls, REST, the long-running job flow
end to end (job + events), and service.json consistency.
"""

import json
import time
from pathlib import Path

import pytest
from _template.capabilities import registry
from _template.store import JobStore
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, DomainEvent, JobStatus
from platform_eventbus import EventBus, EventLog

fastapi = pytest.importorskip("fastapi")
from _template.rest import create_app
from fastapi.testclient import TestClient

USER_CTX = ActorContext(actor=LOCAL_USER)
SERVICE_DIR = Path(__file__).parent.parent


class TestCapabilities:
    async def test_echo(self) -> None:
        result = await execute(registry, "echo", USER_CTX, {"text": "hi", "shout": True})
        assert result == {"echo": "HI"}

    def test_service_json_matches_registry(self) -> None:
        """The service card's capability list must match the registry
        (single source of truth)."""
        card = json.loads((SERVICE_DIR / "service.json").read_text(encoding="utf-8"))
        assert sorted(card["capabilities"]) == registry.names()


@pytest.fixture()
def app(tmp_path):
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    application = create_app(tmp_path, bus=bus)
    application.state.event_log = log
    yield application
    log.close()


class TestRest:
    def test_health(self, app) -> None:
        with TestClient(app) as client:
            resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "up"

    def test_echo_over_http(self, app) -> None:
        with TestClient(app) as client:
            resp = client.post("/capabilities/echo", json={"text": "hi"})
        assert resp.status_code == 200
        assert resp.json() == {"result": {"echo": "hi"}}


class TestJobFlow:
    def test_submit_job_end_to_end(self, app, tmp_path) -> None:
        """Submit -> 202 -> worker executes -> row completed + task.completed event."""
        probe = JobStore(tmp_path / "template.db")  # separate connection for polling
        with TestClient(app) as client:
            resp = client.post("/capabilities/submit_job", json={})
            assert resp.status_code == 202
            job_id = resp.json()["job"]["job_id"]
            deadline = time.time() + 5
            while time.time() < deadline:
                job = probe.get(job_id)
                if job and job["status"] == JobStatus.COMPLETED.value:
                    break
                time.sleep(0.05)
            else:
                pytest.fail("task timed out")
        probe.close()
        log: EventLog = app.state.event_log
        completed = [e for _, e in log.read_after(types=[DomainEvent.TASK_COMPLETED])]
        assert any(e.payload["job_id"] == job_id for e in completed)
