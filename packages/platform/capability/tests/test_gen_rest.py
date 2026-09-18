"""Tests for REST generation: listing, invocation, error mapping, 202, Bearer
auth.
"""

from dataclasses import dataclass

import pytest
from platform_actor import LocalTokenIssuer
from platform_capability import Registry, build_router, capability
from platform_contracts import ActorKind, ActorRef, JobRef

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient


@dataclass
class _EchoIn:
    text: str


@pytest.fixture()
def client(tmp_path):
    reg = Registry("notes")

    @capability(reg, name="echo", description="echo", input_model=_EchoIn)
    def echo(data: _EchoIn) -> dict:
        return {"echo": data.text}

    @capability(reg, name="import_thing", description="long-running task", long_running=True)
    def import_thing() -> JobRef:
        return JobRef(job_id="j-9")

    @capability(reg, name="guarded", description="requires notes.admin", scopes=("notes.admin",))
    def guarded() -> dict:
        return {"secret": True}

    issuer = LocalTokenIssuer(tmp_path / "machine.token")
    app = FastAPI()
    app.include_router(build_router(reg, issuer=issuer))
    client = TestClient(app)
    client.issuer = issuer  # lets tests issue tokens
    return client


class TestRest:
    def test_list(self, client) -> None:
        specs = client.get("/capabilities").json()["capabilities"]
        assert {s["name"] for s in specs} == {"echo", "import_thing", "guarded"}
        echo = next(s for s in specs if s["name"] == "echo")
        assert echo["input"]["required"] == ["text"]

    def test_call_ok(self, client) -> None:
        resp = client.post("/capabilities/echo", json={"text": "hi"})
        assert resp.status_code == 200
        assert resp.json() == {"result": {"echo": "hi"}}

    def test_unknown_404(self, client) -> None:
        resp = client.post("/capabilities/nope", json={})
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOTES.NOT_FOUND"

    def test_invalid_input_400(self, client) -> None:
        resp = client.post("/capabilities/echo", json={"text": 1})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "NOTES.INVALID_INPUT"

    def test_long_running_202(self, client) -> None:
        resp = client.post("/capabilities/import_thing", json={})
        assert resp.status_code == 202
        assert resp.json() == {"job": {"job_id": "j-9", "status": "queued"}}

    def test_agent_scope_forbidden_403(self, client) -> None:
        agent = ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=())
        token = client.issuer.issue(agent)
        resp = client.post(
            "/capabilities/guarded", json={}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "CAPABILITY.FORBIDDEN"

    def test_agent_with_scope_ok(self, client) -> None:
        agent = ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=("notes.admin",))
        token = client.issuer.issue(agent)
        resp = client.post(
            "/capabilities/guarded", json={}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200

    def test_bad_token_401(self, client) -> None:
        resp = client.post(
            "/capabilities/echo",
            json={"text": "x"},
            headers={"Authorization": "Bearer garbage.token"},
        )
        assert resp.status_code == 401

    def test_local_user_default(self, client) -> None:
        # no token -> local single-user; user actors are always trusted, so guarded passes too
        resp = client.post("/capabilities/guarded", json={})
        assert resp.status_code == 200

    def test_unparseable_body_400(self, client) -> None:
        """A body that fails JSON parsing is a 400 INVALID_INPUT, never a
        silent rewrite to {} that resurfaces as 'missing required inputs'."""
        resp = client.post(
            "/capabilities/echo", content=b"not json", headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "NOTES.INVALID_INPUT"

    def test_non_object_body_400(self, client) -> None:
        resp = client.post(
            "/capabilities/echo", content=b"[1,2]", headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "NOTES.INVALID_INPUT"
