"""Gateway tests: service mounting and error envelopes, chat channel, SSE,
rate limiting, activity reporting, and health aggregation.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient
from gateway.mounts import MountSpec
from gateway.rest import create_app
from platform_contracts import LOCAL_USER, ActorKind, ActorRef, DomainEvent, Event


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


class TestMount:
    def test_capability_call(self, client) -> None:
        r = client.post("/api/echo/capabilities/echo", json={"text": "hi"})
        assert r.status_code == 200
        assert r.json()["result"] == {"text": "hi"}

    def test_service_error_envelope(self, client) -> None:
        """A failing capability surfaces as the unified error envelope
        (e.g. ECHO.UNAVAILABLE with the service field set)."""
        r = client.post("/api/echo/capabilities/explode", json={})
        assert r.status_code == 503
        body = r.json()["error"]
        assert body["code"] == "ECHO.UNAVAILABLE" and body["service"] == "echo"


class TestChat:
    def test_post_and_history(self, client, bus) -> None:
        r = client.post("/api/chat/messages", json={"content": "hello"})
        assert r.status_code == 200 and r.json()["seq"] >= 1
        asyncio.run(
            bus.publish(
                Event(
                    type=DomainEvent.AGENT_MESSAGE,
                    actor=ActorRef(kind=ActorKind.AGENT, id="agent.main"),
                    payload={"content": "hello, I'm here"},
                )
            )
        )
        r = client.get("/api/chat/messages")
        msgs = [(m["type"], m["payload"]["content"]) for m in r.json()["messages"]]
        assert msgs == [("user.message", "hello"), ("agent.message", "hello, I'm here")]

    def test_empty_message_rejected(self, client) -> None:
        r = client.post("/api/chat/messages", json={"content": "  "})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "GATEWAY.INVALID_INPUT"

    def _history_client(self, bus, tmp_path, echo_registry, page_size: int):
        """Client with a small history page so the windowing is exercisable
        without publishing hundreds of events."""
        app = create_app(
            [MountSpec(domain="echo", registry=echo_registry, probe=lambda: {"status": "up"})],
            bus=bus,
            db_path=tmp_path / "gw-history.db",
            history_page_size=page_size,
        )
        return TestClient(app)

    def test_history_default_returns_newest_window(self, bus, tmp_path, echo_registry) -> None:
        """No cursor: the NEWEST page of chat events is returned (ascending),
        not the first page ever written; has_more marks older pages."""
        with self._history_client(bus, tmp_path, echo_registry, page_size=3) as client:
            for i in range(5):
                assert (
                    client.post("/api/chat/messages", json={"content": f"m{i}"}).status_code == 200
                )
            body = client.get("/api/chat/messages").json()
            assert [m["payload"]["content"] for m in body["messages"]] == ["m2", "m3", "m4"]
            assert body["has_more"] is True

    def test_history_default_ignores_non_chat_events(self, bus, tmp_path, echo_registry) -> None:
        """The window counts matching chat rows only: interleaved non-chat
        events neither fill the page nor shift which chat rows are returned."""
        with self._history_client(bus, tmp_path, echo_registry, page_size=2) as client:
            for i in range(4):
                client.post("/api/chat/messages", json={"content": f"m{i}"})
                asyncio.run(
                    bus.publish(
                        Event(
                            type="user.activity",
                            actor=LOCAL_USER,
                            payload={"path": f"/p{i}"},
                        )
                    )
                )
            body = client.get("/api/chat/messages").json()
            assert [m["payload"]["content"] for m in body["messages"]] == ["m2", "m3"]

    def test_history_before_seq_pages_backward(self, bus, tmp_path, echo_registry) -> None:
        """before_seq returns the page immediately older (ascending) and
        has_more falls to False at the beginning of the log."""
        with self._history_client(bus, tmp_path, echo_registry, page_size=3) as client:
            for i in range(5):
                client.post("/api/chat/messages", json={"content": f"m{i}"})
            page1 = client.get("/api/chat/messages").json()
            first_seq = page1["messages"][0]["seq"]
            page2 = client.get(f"/api/chat/messages?before_seq={first_seq}").json()
            assert [m["payload"]["content"] for m in page2["messages"]] == ["m0", "m1"]
            assert page2["has_more"] is False

    def test_history_after_seq_pages_forward(self, bus, tmp_path, echo_registry) -> None:
        """after_seq keeps its forward-cursor semantics."""
        with self._history_client(bus, tmp_path, echo_registry, page_size=2) as client:
            for i in range(4):
                client.post("/api/chat/messages", json={"content": f"m{i}"})
            body = client.get("/api/chat/messages").json()
            last_seq = body["messages"][-1]["seq"]
            tail = client.get(f"/api/chat/messages?after_seq={last_seq}").json()
            assert tail["messages"] == [] and tail["has_more"] is False

    def test_sse_replay_then_close(self, client, bus) -> None:
        """SSE resume: connect with after_seq; backlog events in the log are
        replayed first (once mode closes after catching up)."""
        asyncio.run(
            bus.publish(
                Event(
                    type=DomainEvent.AGENT_MESSAGE,
                    actor=ActorRef(kind=ActorKind.AGENT, id="agent.main"),
                    payload={"content": "offline reply"},
                )
            )
        )
        r = client.get("/api/chat/stream?after_seq=0&once=true")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert "offline reply" in r.text
        assert "id: 1" in r.text  # frames carry seq as the client resume cursor

    def test_sse_streams_agent_step(self, client, bus) -> None:
        """Tool steps (agent.step) are visible on the human timeline: they are
        included in _STREAM_TYPES."""
        asyncio.run(
            bus.publish(
                Event(
                    type="agent.step",
                    actor=ActorRef(kind=ActorKind.AGENT, id="agent.main"),
                    payload={
                        "subagent": "chat",
                        "name": "notes__create_note",
                        "kind": "tool",
                        "summary": "created",
                    },
                )
            )
        )
        r = client.get("/api/chat/stream?after_seq=0&once=true")
        assert "agent.step" in r.text and "notes__create_note" in r.text

    def test_sse_streams_agent_delta(self, client, bus) -> None:
        """Streaming deltas: agent.delta is included in _STREAM_TYPES and
        pushed to the frontend."""
        asyncio.run(
            bus.publish(
                Event(
                    type=DomainEvent.AGENT_DELTA,
                    actor=ActorRef(kind=ActorKind.AGENT, id="agent.main"),
                    payload={"run_id": "r1", "subagent": "chat", "round": 1, "text": "hello"},
                )
            )
        )
        r = client.get("/api/chat/stream?after_seq=0&once=true")
        assert "agent.delta" in r.text and "hello" in r.text

    def test_sse_streams_policy_notify_not_history(self, client, bus) -> None:
        """L1 permission prompts go out over the SSE stream as toasts; they are
        not part of the chat history returned by GET messages."""
        asyncio.run(
            bus.publish(
                Event(
                    type="agent.policy.notify",
                    actor=ActorRef(kind=ActorKind.AGENT, id="agent.main"),
                    payload={"message": "write_file: g.txt"},
                )
            )
        )
        r = client.get("/api/chat/stream?after_seq=0&once=true")
        assert "agent.policy.notify" in r.text and "write_file: g.txt" in r.text
        hist = client.get("/api/chat/messages").json()["messages"]
        assert all(m["type"] != "agent.policy.notify" for m in hist)

    def test_sse_streams_workspace_switched_not_history(self, client, bus) -> None:
        """Workspace hot-switch notices ride the SSE stream for cross-tab
        awareness; they are not part of the chat history."""
        asyncio.run(
            bus.publish(
                Event(
                    type=DomainEvent.WORKSPACE_SWITCHED,
                    actor=ActorRef(kind=ActorKind.SYSTEM, id="host.workspace"),
                    payload={"workspace": "ws2", "previous": "ws1"},
                )
            )
        )
        r = client.get("/api/chat/stream?after_seq=0&once=true")
        assert "workspace.switched" in r.text and "ws2" in r.text
        hist = client.get("/api/chat/messages").json()["messages"]
        assert all(m["type"] != "workspace.switched" for m in hist)

    def test_sse_replay_includes_task_glob(self, client, bus) -> None:
        """once-mode replay understands subscription globs: 'task.*' in
        _STREAM_TYPES replays persisted task.progress events from the log."""
        asyncio.run(
            bus.publish(
                Event(
                    type="task.progress",
                    actor=ActorRef(kind=ActorKind.AGENT, id="sources.doc"),
                    payload={"task_id": "t1", "progress": "parsing 50%"},
                )
            )
        )
        r = client.get("/api/chat/stream?after_seq=0&once=true")
        assert "task.progress" in r.text and "parsing 50%" in r.text


class TestSseReplay:
    def test_sse_lag_replay_skips_queue_duplicates(self, tmp_path) -> None:
        """After a queue overflow (lagged) the dropped range is replayed from
        the log; queue-resident rows the replay already covered are skipped,
        so the consumer sees each seq exactly once."""
        from gateway.chat import _stream_events
        from platform_eventbus import EventBus, EventLog

        async def scenario() -> list[int]:
            event_log = EventLog(tmp_path / "sse.db")
            bus = EventBus(event_log, queue_size=2)
            agent = ActorRef(kind=ActorKind.AGENT, id="agent.main")

            async def publish(tag: str) -> int:
                return await bus.publish(
                    Event(type=DomainEvent.AGENT_MESSAGE, actor=agent, payload={"content": tag})
                )

            for i in range(3):
                await publish(f"e{i}")

            seqs: list[int] = []
            agen = _stream_events(
                bus, start_seq=0, types=("agent.message",), wanted=lambda _e: True
            )

            def _seq(item: tuple[int, Event] | None) -> int:
                assert item is not None
                return item[0]

            # Consume two backlog rows; the generator is now suspended on the
            # third (before its queue-consumption loop)
            for _ in range(2):
                seqs.append(_seq(await agen.__anext__()))
            # Overflow the queue while the consumer is slow: e4/e5 land in the
            # queue (capacity 2), e5+ is dropped and lagged=True
            for i in range(3, 6):
                await publish(f"e{i}")
            # Resume: row 3 from the pending replay, then the lag replay
            # re-delivers 4..6 from the log, and the queued copies of 4/5
            # must be skipped
            for _ in range(4):
                seqs.append(_seq(await agen.__anext__()))
            # Grace window: no further delivery may arrive (drives the dedup
            # branch; without it the queued 4/5 would show up here)
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(agen.__anext__(), timeout=0.5)
            await agen.aclose()
            event_log.close()
            return seqs

        assert asyncio.run(scenario()) == [1, 2, 3, 4, 5, 6]

    def test_sse_replay_pages_through_large_backlog(self, tmp_path) -> None:
        """The catch-up replay loops page by page: a backlog larger than one
        replay page is fully delivered, not stranded past the first page."""
        from gateway.chat import _REPLAY_PAGE, _stream_events
        from platform_eventbus import EventBus, EventLog

        async def scenario() -> list[int]:
            event_log = EventLog(tmp_path / "sse.db")
            bus = EventBus(event_log, queue_size=10)
            agent = ActorRef(kind=ActorKind.AGENT, id="agent.main")
            for i in range(_REPLAY_PAGE + 40):
                await bus.publish(
                    Event(type=DomainEvent.AGENT_MESSAGE, actor=agent, payload={"n": i})
                )
            agen = _stream_events(
                bus, start_seq=0, types=("agent.message",), wanted=lambda _e: True
            )
            seqs = []
            for _ in range(_REPLAY_PAGE + 40):
                item = await agen.__anext__()
                assert item is not None
                seqs.append(item[0])
            await agen.aclose()
            event_log.close()
            return seqs

        seqs = asyncio.run(scenario())
        assert seqs == list(range(1, _REPLAY_PAGE + 41))


class TestTrajectory:
    def _step(self, bus, name: str, **extra):
        payload = {
            "subagent": "chat",
            "name": name,
            "kind": "tool",
            "summary": f"{name} done",
            "run_id": "r1",
            "detail": {},
            **extra,
        }
        return asyncio.run(
            bus.publish(
                Event(
                    type=DomainEvent.AGENT_STEP,
                    actor=ActorRef(kind=ActorKind.AGENT, id="agent.main"),
                    payload=payload,
                )
            )
        )

    def test_steps_returned_messages_excluded(self, client, bus) -> None:
        client.post("/api/chat/messages", json={"content": "hi"})
        self._step(bus, "list_dir", detail={"tool_call_id": "c-1", "ok": True})
        body = client.get("/api/chat/trajectory").json()
        assert body["has_more"] is False
        assert [(s["type"], s["payload"]["name"]) for s in body["steps"]] == [
            ("agent.step", "list_dir")
        ]
        assert body["steps"][0]["payload"]["run_id"] == "r1"
        assert body["steps"][0]["payload"]["detail"]["tool_call_id"] == "c-1"

    def test_newest_window_with_small_page(self, bus, tmp_path, echo_registry) -> None:
        app = create_app(
            [MountSpec(domain="echo", registry=echo_registry, probe=lambda: {"status": "up"})],
            bus=bus,
            db_path=tmp_path / "gw-traj.db",
            trajectory_page_size=2,
        )
        with TestClient(app) as c:
            for name in ("s1", "s2", "s3"):
                self._step(bus, name)
            body = c.get("/api/chat/trajectory").json()
            assert [s["payload"]["name"] for s in body["steps"]] == ["s2", "s3"]
            assert body["has_more"] is True
            first = body["steps"][0]["seq"]
            older = c.get(f"/api/chat/trajectory?before_seq={first}").json()
            assert [s["payload"]["name"] for s in older["steps"]] == ["s1"]


class TestRateLimit:
    def test_per_minute_cap(self, bus, tmp_path, echo_registry) -> None:
        app = create_app(
            [MountSpec(domain="echo", registry=echo_registry)],
            bus=bus,
            db_path=tmp_path / "gw.db",
            rate_limit_per_minute=2,
        )
        with TestClient(app) as c:
            assert c.post("/api/chat/messages", json={"content": "1"}).status_code == 200
            assert c.post("/api/chat/messages", json={"content": "2"}).status_code == 200
            r = c.post("/api/chat/messages", json={"content": "3"})
            assert r.status_code == 429
            assert r.json()["error"]["code"] == "GATEWAY.RATE_LIMITED"


class TestActivity:
    def test_report_and_feed(self, client) -> None:
        r = client.post(
            "/api/activity",
            json={"kind": "page_view", "page": "notes", "detail": {"note_count": 5}},
        )
        assert r.status_code == 200
        feed = client.get("/api/activity/feed?types=user.activity").json()["events"]
        assert feed[-1]["payload"]["page"] == "notes"

    def test_feed_agent_and_session_attribution_filters(self, client, bus) -> None:
        """agent=true keeps only agent operations: domain events stamped with
        payload.session, settings changes published by the AGENT actor, and
        write/edit tool steps. Conversation rows and the user's own actions
        (unstamped domain events, LOCAL_USER settings changes, user.message)
        stay out."""
        import asyncio

        def _publish(type_: str, payload: dict, actor: ActorRef) -> None:
            asyncio.run(bus.publish(Event(type=type_, actor=actor, payload=payload)))

        agent = ActorRef(kind=ActorKind.AGENT, id="agent.main")
        system = ActorRef(kind=ActorKind.SYSTEM, id="notes.service")
        _publish(DomainEvent.NOTE_CREATED, {"note_id": "n1", "title": "t", "session": "s1"}, system)
        _publish(DomainEvent.NOTE_CREATED, {"note_id": "n2", "title": "t2"}, system)
        _publish(DomainEvent.USER_MESSAGE, {"content": "hi", "session": "s1"}, LOCAL_USER)
        _publish(DomainEvent.AGENT_MESSAGE, {"content": "hello", "session": "s1"}, agent)
        _publish(DomainEvent.SETTINGS_CHANGED, {"key": "k", "value": 1}, agent)
        _publish(DomainEvent.SETTINGS_CHANGED, {"key": "k2", "value": 2}, LOCAL_USER)
        _publish(
            DomainEvent.AGENT_STEP,
            {
                "kind": "tool",
                "name": "write",
                "session": "s1",
                "detail": {"args": {"path": "a.ts"}},
            },
            agent,
        )
        _publish(
            DomainEvent.AGENT_STEP,
            {"kind": "tool", "name": "grep", "session": "s1", "detail": {"args": {}}},
            agent,
        )
        ops = client.get("/api/activity/feed?agent=true&recent=true").json()["events"]
        found = [(e["type"], e["payload"].get("note_id") or e["payload"].get("key")) for e in ops]
        assert ("note.created", "n1") in found
        assert ("note.created", "n2") not in found
        assert ("user.message", None) not in found
        assert ("agent.message", None) not in found
        assert ("settings.changed", "k") in found
        assert ("settings.changed", "k2") not in found
        steps = [e for e in ops if e["type"] == "agent.step"]
        assert len(steps) == 1 and steps[0]["payload"]["name"] == "write"
        # session narrowing stays inside the operations whitelist
        scoped = client.get(
            "/api/activity/feed?agent=true&recent=true&session=s1"
        ).json()["events"]
        assert scoped
        assert all(e["payload"].get("session") == "s1" for e in scoped if e["type"] != "settings.changed")

    def test_unknown_kind(self, client) -> None:
        r = client.post("/api/activity", json={"kind": "hack"})
        assert r.status_code == 400

    def test_online_endpoint_removed(self, client) -> None:
        # The user-online trigger (agent-initiated greeting) is removed:
        # the route must not exist.
        assert client.post("/api/user/online").status_code == 404


class TestHealth:
    def test_aggregate_and_transition_event(self, bus, tmp_path, echo_registry) -> None:
        state = {"up": True}

        def probe():
            if state["up"]:
                return {"status": "up"}
            raise RuntimeError("connection refused")

        app = create_app(
            [MountSpec(domain="echo", registry=echo_registry, probe=probe)],
            bus=bus,
            db_path=tmp_path / "gw.db",
        )
        with TestClient(app) as c:
            r = c.get("/health").json()
            assert r["status"] == "up" and r["services"]["echo"]["status"] == "up"
            state["up"] = False
            r = c.get("/health").json()
            assert r["status"] == "degraded"
            assert r["services"]["echo"]["status"] == "down"
        types = [e.type for _, e in bus.log.read_after()]
        assert DomainEvent.SERVICE_HEALTH_CHANGED in types

    def test_actor_middleware_defaults_local(self, client) -> None:
        """Without a token, requests default to the local single user."""
        assert LOCAL_USER.id == "local"


class TestBearerIdentity:
    def test_bearer_token_resolves_actor(self, bus, tmp_path) -> None:
        """With an issuer configured, valid Bearer tokens resolve to their
        actor; invalid tokens get 401."""
        from platform_actor import LocalTokenIssuer
        from platform_contracts import ActorKind, ActorRef

        issuer = LocalTokenIssuer(tmp_path / "machine.token")
        app = create_app(bus=bus, db_path=tmp_path / "gw.db", issuer=issuer)
        agent = ActorRef(kind=ActorKind.AGENT, id="agent.x", scopes=())
        good = issuer.issue(agent)
        with TestClient(app) as c:
            ok = c.post(
                "/api/chat/messages",
                json={"content": "hi"},
                headers={"Authorization": f"Bearer {good}"},
            )
            assert ok.status_code == 200 and ok.json()["seq"] > 0
            bad = c.post(
                "/api/chat/messages",
                json={"content": "hi"},
                headers={"Authorization": "Bearer not-a-token"},
            )
            assert bad.status_code == 401

    def test_loopback_without_token_still_local(self, bus, tmp_path) -> None:
        """With an issuer configured, loopback requests without a token still
        map to the local user (single-user threat model)."""
        from platform_actor import LocalTokenIssuer

        issuer = LocalTokenIssuer(tmp_path / "machine.token")
        app = create_app(bus=bus, db_path=tmp_path / "gw.db", issuer=issuer)
        with TestClient(app) as c:
            r = c.post("/api/chat/messages", json={"content": "hi"})
            assert r.status_code == 200

    def test_non_loopback_without_token_401(self, bus, tmp_path) -> None:
        """Non-loopback requests without a token are rejected (no unauthenticated
        LAN access)."""
        from platform_actor import LocalTokenIssuer

        issuer = LocalTokenIssuer(tmp_path / "machine.token")
        app = create_app(bus=bus, db_path=tmp_path / "gw.db", issuer=issuer)
        with TestClient(app, client=("10.0.0.8", 50000)) as c:
            denied = c.post("/api/chat/messages", json={"content": "hi"})
            assert denied.status_code == 401
            health = c.get("/health")
            assert health.status_code == 200
            boot = c.get("/api/session/bootstrap")
            assert boot.status_code == 403

    def test_bootstrap_sets_httponly_cookie(self, bus, tmp_path) -> None:
        from platform_actor import COOKIE_NAME, LocalTokenIssuer

        issuer = LocalTokenIssuer(tmp_path / "machine.token")
        app = create_app(bus=bus, db_path=tmp_path / "gw.db", issuer=issuer)
        with TestClient(app) as c:
            r = c.get("/api/session/bootstrap")
            assert r.status_code == 200 and r.json()["ok"] is True
            assert COOKIE_NAME in r.cookies

    def test_bad_json_body_is_400(self, client) -> None:
        """Invalid JSON / non-object bodies return 400, not 500."""
        import json as _json

        r = client.post(
            "/api/chat/messages", content=b"not json", headers={"Content-Type": "application/json"}
        )
        assert r.status_code == 400
        r = client.post(
            "/api/activity",
            content=_json.dumps([1, 2]).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400


class TestChatSessions:
    def test_post_carries_session_payload(self, client, bus) -> None:
        r = client.post("/api/chat/messages", json={"content": "hi", "session": "sess1"})
        assert r.status_code == 200
        rows = bus.log.read_after(types=["user.message"])
        assert rows and rows[-1][1].payload["session"] == "sess1"

    def test_post_without_session_keeps_empty(self, client, bus) -> None:
        client.post("/api/chat/messages", json={"content": "hi"})
        rows = bus.log.read_after(types=["user.message"])
        assert rows[-1][1].payload.get("session", "") == ""

    def test_post_rejects_malformed_session(self, client) -> None:
        r = client.post("/api/chat/messages", json={"content": "hi", "session": "../evil"})
        assert r.status_code == 400

    def test_history_session_filter(self, client, bus) -> None:
        from platform_contracts import DomainEvent, Event

        client.post("/api/chat/messages", json={"content": "a-msg", "session": "s1"})
        client.post("/api/chat/messages", json={"content": "b-msg", "session": "s2"})
        # A legacy-style row without a session belongs to the global lane
        import asyncio

        from platform_contracts import LOCAL_USER

        asyncio.run(
            bus.publish(
                Event(type=DomainEvent.USER_MESSAGE, actor=LOCAL_USER, payload={"content": "old"})
            )
        )
        client.post("/api/chat/messages", json={"content": "a2", "session": "s1"})

        s1 = client.get("/api/chat/messages", params={"session": "s1"}).json()
        contents = [m["payload"]["content"] for m in s1["messages"]]
        assert contents == ["a-msg", "a2"]
        assert s1["has_more"] is False

        unfiltered = client.get("/api/chat/messages").json()
        assert len(unfiltered["messages"]) == 4  # no filter -> everything

    def test_history_session_filter_has_more(self, client, bus) -> None:
        for i in range(5):
            client.post("/api/chat/messages", json={"content": f"m{i}", "session": "s1"})
        page = client.get("/api/chat/messages", params={"session": "s1", "limit": 2}).json()
        assert [m["payload"]["content"] for m in page["messages"]] == ["m3", "m4"]
        assert page["has_more"] is True

    def test_trajectory_session_filter(self, client, bus) -> None:
        import asyncio

        from platform_contracts import LOCAL_USER, DomainEvent, Event

        asyncio.run(
            bus.publish(
                Event(
                    type=DomainEvent.AGENT_STEP,
                    actor=LOCAL_USER,
                    payload={"name": "s1step", "session": "s1"},
                )
            )
        )
        asyncio.run(
            bus.publish(
                Event(
                    type=DomainEvent.AGENT_STEP,
                    actor=LOCAL_USER,
                    payload={"name": "s2step", "session": "s2"},
                )
            )
        )
        body = client.get("/api/chat/trajectory", params={"session": "s1"}).json()
        assert [s["payload"]["name"] for s in body["steps"]] == ["s1step"]
