"""Chat and activity channel edge branches, driven over httpx ASGITransport
with the gateway's HTTP middleware stack removed.

Why no middleware: starlette's BaseHTTPMiddleware runs the downstream app in
a child task, and on this stack (CPython 3.11 + coverage 7.x on Windows) the
tracer loses the sync statements of handlers behind it — tests still pass
but report phantom misses. Clearing the stack makes coverage truthful for
these branches; auth resolution and security headers are covered separately
by the TestClient-based suite (test_gateway.py). Happy paths run before the
first handled error for the same tracing reason.
"""

from __future__ import annotations

from typing import Any, cast

import httpx
import pytest
from gateway.rest import create_app
from platform_contracts import ActorKind, ActorRef, DomainEvent, Event
from platform_eventbus import EventBus, EventLog

_JSON_HEADERS = {"Content-Type": "application/json"}


@pytest.fixture()
def bus(tmp_path):
    return EventBus(EventLog(tmp_path / "events.db"))


@pytest.fixture()
def app(bus, tmp_path):
    application = create_app(bus=bus, db_path=tmp_path / "gw.db")
    application.user_middleware.clear()
    return application


async def _pub(bus: EventBus, type_: str, payload: dict[str, Any]) -> None:
    await bus.publish(
        Event(
            type=type_,
            actor=ActorRef(kind=ActorKind.AGENT, id="agent.main"),
            payload=payload,
        )
    )


class TestHappyPathsFirst:
    async def test_report_activity_defaults_detail(self, app) -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.post("/api/activity", json={"kind": "pointer", "page": "/p"})
            assert r.status_code == 200 and r.json()["seq"] >= 1
            feed = (await client.get("/api/activity/feed?types=user.activity")).json()["events"]
        assert feed[-1]["payload"]["detail"] == {}

    async def test_post_chat_message_publishes(self, app) -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.post("/api/chat/messages", json={"content": "hello"})
        assert r.status_code == 200 and r.json()["seq"] >= 1


class TestChannelValidation:
    async def test_activity_rejects_bad_json_and_non_object(self, app) -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.post("/api/activity", content=b"not json", headers=_JSON_HEADERS)
            assert r.status_code == 400
            r = await client.post("/api/activity", content=b"[1]", headers=_JSON_HEADERS)
            assert r.status_code == 400

    async def test_activity_rejects_non_object_detail(self, app) -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            for detail in ("str-detail", [1, 2], 7):
                r = await client.post(
                    "/api/activity", json={"kind": "selection", "page": "/p", "detail": detail}
                )
                assert r.status_code == 400

    async def test_chat_rejects_non_object_body(self, app) -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.post("/api/chat/messages", content=b"[1, 2]", headers=_JSON_HEADERS)
            assert r.status_code == 400

    async def test_chat_rejects_empty_content(self, app) -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.post("/api/chat/messages", json={"content": "   "})
        assert r.status_code == 400

    async def test_activity_rejects_unknown_kind_with_hint(self, app) -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.post("/api/activity", json={"kind": "hack"})
        assert r.status_code == 400
        body = r.json()["error"]
        assert body["code"] == "GATEWAY.INVALID_INPUT" and "allowed" in (body.get("hint") or "")


class TestActivityFeedFilters:
    async def test_forward_agent_filter_keeps_operations_only(self, app, bus) -> None:
        """agent=true in forward mode filters in memory after the SQL read:
        conversation rows and unstamped domain events stay out even though
        the query had to read them."""
        await _pub(bus, DomainEvent.USER_MESSAGE, {"content": "hi", "session": "s1"})
        await _pub(bus, DomainEvent.NOTE_CREATED, {"note_id": "n1", "session": "s1"})
        await _pub(bus, DomainEvent.NOTE_CREATED, {"note_id": "n2"})  # no session stamp
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            ops = (await client.get("/api/activity/feed?agent=true")).json()["events"]
        assert [e["payload"].get("note_id") for e in ops] == ["n1"]

    async def test_feed_skips_non_object_payload_rows(self, app, bus) -> None:
        """Rows written with a non-object payload (corrupt/legacy) are skipped
        by the feed scan instead of raising mid-read."""
        await bus.publish(
            Event(
                type=DomainEvent.NOTE_CREATED,
                actor=ActorRef(kind=ActorKind.AGENT, id="agent.main"),
                # simulate a corrupt/legacy row: the payload is not an object
                payload=cast(Any, ["corrupt"]),
            )
        )
        await _pub(bus, DomainEvent.NOTE_CREATED, {"note_id": "n-ok", "session": "s1"})
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            ops = (await client.get("/api/activity/feed?agent=true&recent=true")).json()["events"]
        assert [e["payload"].get("note_id") for e in ops] == ["n-ok"]

    async def test_recent_stops_early_once_window_is_full(self, app, bus) -> None:
        """The bounded backfill loop stops as soon as the newest-limit window
        is full of attributed operations."""
        for i in range(5):
            await _pub(bus, DomainEvent.NOTE_CREATED, {"note_id": f"n{i}", "session": "s1"})
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            body = (await client.get("/api/activity/feed?agent=true&recent=true&limit=3")).json()
        assert [e["payload"]["note_id"] for e in body["events"]] == ["n2", "n3", "n4"]

    async def test_session_narrowing_implies_agent_filter(self, app, bus) -> None:
        """session=<id> is an operations read by contract: conversation
        traffic never leaks through a session-scoped query."""
        await _pub(bus, DomainEvent.AGENT_MESSAGE, {"content": "chat", "session": "s1"})
        await _pub(bus, DomainEvent.NOTE_CREATED, {"note_id": "n1", "session": "s1"})
        await _pub(bus, DomainEvent.NOTE_CREATED, {"note_id": "n2", "session": "s2"})
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            ops = (await client.get("/api/activity/feed?session=s1&recent=true")).json()["events"]
        assert [e["payload"].get("note_id") for e in ops] == ["n1"]

    async def test_limit_floor_is_one(self, app, bus) -> None:
        await _pub(bus, DomainEvent.NOTE_CREATED, {"note_id": "n0", "session": "s1"})
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            events = (await client.get("/api/activity/feed?limit=0")).json()["events"]
        assert len(events) == 1
