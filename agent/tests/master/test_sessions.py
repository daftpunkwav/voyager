"""Tests for multi-session: the session manager's lifecycle
(create/fork/rename/delete/active pointer/lazy restore) and Master's
per-session routing (isolation of arbitration, unknown-id auto-create,
session-scoped replies).
"""

import asyncio

import pytest
from agent.llm import FakeLLM
from agent.main import build_agent
from agent.master.master import _Queued
from agent.memory.session_store import SessionSnapshot
from agent.runtime.state import RunStatus
from platform_contracts import DomainEvent, ServiceError


def _app(tmp_path, llm):
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm)
    return app


class TestSessionManager:
    def test_create_list_rename_delete(self, tmp_path) -> None:
        app = _app(tmp_path, FakeLLM())
        try:
            mgr = app.master.sessions
            created = mgr.create(title="工作")
            sid = created["session_id"]
            rows = mgr.list()
            assert [r["title"] for r in rows] == ["工作"]
            mgr.rename(sid, "工作改名")
            assert mgr.list()[0]["title"] == "工作改名"
            mgr.delete(sid)
            assert mgr.list() == []
        finally:
            app.close()

    def test_delete_running_refused(self, tmp_path) -> None:
        app = _app(tmp_path, FakeLLM())
        try:
            mgr = app.master.sessions
            inst = mgr.resolve("")
            inst.state.status = RunStatus.RUNNING
            with pytest.raises(ServiceError):
                mgr.delete(inst.session)
        finally:
            app.close()

    def test_delete_drops_queued_inbox(self, tmp_path) -> None:
        """Deleting a session drops its queued-message inbox: messages parked
        while its turn was running belong to the dead conversation and must
        never drain into a later session recreated with the same id."""
        app = _app(tmp_path, FakeLLM())
        try:
            mgr = app.master.sessions
            created = mgr.create(title="短命会话")
            sid = created["session_id"]
            app.master._session_inbox(sid).append(_Queued("排队消息"))
            mgr.delete(sid)
            assert app.master._inboxes.get(sid) is None
        finally:
            app.close()

    def test_delete_lands_session_deleted_event(self, tmp_path) -> None:
        """session.deleted carries the deleted session's title; when the delete
        happened inside a chat turn (capability invocation context set) the
        payload.session marks the agent as the driver, human deletes stay
        session-less."""
        from platform_capability import current_chat_session
        from platform_eventbus import EventBus, EventLog

        app = _app(tmp_path, FakeLLM())
        try:
            mgr = app.master.sessions
            created = mgr.create(title="短命会话")
            sid = created["session_id"]
            bus = EventBus(EventLog(tmp_path / "rd" / "events.db"))
            try:
                mgr.delete(sid)
                rows = bus.log.read_after(types=("session.deleted",), limit=10)
                assert rows, "session.deleted must land in the event log"
                (_, ev) = rows[-1]
                assert ev.payload["deleted"] == sid
                assert ev.payload["title"] == "短命会话"
                # human path (no invocation context): no session stamp
                assert "session" not in ev.payload

                created2 = mgr.create(title="另一个")
                token = current_chat_session.set("sess-driver")
                try:
                    mgr.delete(created2["session_id"])
                finally:
                    current_chat_session.reset(token)
                rows = bus.log.read_after(types=("session.deleted",), limit=10)
                (_, ev2) = rows[-1]
                assert ev2.payload["session"] == "sess-driver"
            finally:
                bus.log.close()
        finally:
            app.close()

    def test_fork_copies_history(self, tmp_path) -> None:
        app = _app(tmp_path, FakeLLM(default="Got it."))
        try:
            mgr = app.master.sessions
            source = mgr.resolve("")
            source.history.append({"role": "user", "content": "原始上下文"})
            mgr.persist(source.session)
            created = mgr.fork("")
            forked = mgr.instance_for(created["session_id"])
            assert forked is not None
            assert any(m.get("content") == "原始上下文" for m in forked.history)
            # The source stays untouched
            assert forked.session != source.session
        finally:
            app.close()

    def test_curation_flags_survive_rename_and_persist(self, tmp_path) -> None:
        """Pin/archive must survive a rename and per-turn persistence: both
        rewrite the snapshot, and dropping the flags there would silently
        unpin the session on the next chat message."""
        app = _app(tmp_path, FakeLLM())
        try:
            mgr = app.master.sessions
            created = mgr.create(title="工作")
            sid = created["session_id"]
            mgr.set_flags(sid, pinned=True)
            inst = mgr.resolve(sid)
            inst.history.append({"role": "user", "content": "你好"})
            mgr.persist(sid)
            mgr.rename(sid, "工作改名")
            row = next(r for r in mgr.list() if r["session_id"] == sid)
            assert row["title"] == "工作改名"
            assert row["pinned"] is True
            assert row["archived"] is False
        finally:
            app.close()

    def test_active_pointer_and_switch(self, tmp_path) -> None:
        app = _app(tmp_path, FakeLLM())
        try:
            mgr = app.master.sessions
            first = mgr.resolve("")
            created = mgr.create(title="second")
            # Active is still the first session
            assert mgr.active_id() == first.session
            mgr.set_active(created["session_id"])
            assert mgr.active_id() == created["session_id"]
            # Listing marks the active row
            assert [r["active"] for r in mgr.list()] == [True, False] or any(
                r["active"] and r["session_id"] == created["session_id"] for r in mgr.list()
            )
        finally:
            app.close()

    def test_lazy_restore_from_store(self, tmp_path) -> None:
        """A session known only to the store (no live instance) is rebuilt on
        first use with its history intact."""
        app = _app(tmp_path, FakeLLM())
        try:
            store = app.master.sessions._store
            store.save(
                SessionSnapshot(
                    session_id="stored1",
                    title="磁盘会话",
                    persona="recon",
                    goal="g",
                    history=[{"role": "user", "content": "旧消息"}],
                )
            )
            inst = app.master.sessions.instance_for("stored1")
            assert inst is not None
            assert inst.history[0]["content"] == "旧消息"
            assert inst.task.conversational is True
            assert inst.persona == "recon"
        finally:
            app.close()


class TestSessionRouting:
    async def test_unknown_session_id_auto_creates(self, tmp_path, agent_replies, settle) -> None:
        """A message with an unknown explicit session id creates the session
        instead of losing the message."""
        app = _app(tmp_path, FakeLLM(default="Got it."))
        try:
            await app.master.handle_user_message("你好", session_id="fresh01")
            await settle(app)
            assert app.master.sessions.instance_for("fresh01") is not None
            assert agent_replies(app) == ["Got it."]
        finally:
            app.close()

    async def test_explicit_session_targets_isolated_instances(
        self, tmp_path, agent_replies, settle
    ) -> None:
        app = _app(tmp_path, FakeLLM(default="Got it."))
        try:
            await app.master.handle_user_message("甲会话", session_id="sess-a")
            await settle(app)
            await app.master.handle_user_message("乙会话", session_id="sess-b")
            await settle(app)
            a = app.master.sessions.instance_for("sess-a")
            b = app.master.sessions.instance_for("sess-b")
            assert a is not b
            assert [m["content"] for m in a.history if m["role"] == "user"] == ["甲会话"]
            assert [m["content"] for m in b.history if m["role"] == "user"] == ["乙会话"]
        finally:
            app.close()

    async def test_running_session_queues_without_blocking_another(
        self, tmp_path, agent_replies, settle
    ) -> None:
        """While session A is busy, a message to A queues (queue mode) but a
        message to B starts immediately - arbitration is per session."""
        app = _app(tmp_path, FakeLLM(default="Got it."))
        try:
            await app.master.handle_user_message("开始", session_id="sess-a")
            await settle(app)
            app.master.sessions.instance_for("sess-a").state.status = RunStatus.RUNNING
            await app.master.handle_user_message("排队", session_id="sess-a")
            await asyncio.sleep(0)
            assert app.master._inboxes.get("sess-a") is not None
            # B is free: its turn runs even though A is mid-turn
            await app.master.handle_user_message("立即", session_id="sess-b")
            await settle(app)
            assert agent_replies(app).count("Got it.") == 2
        finally:
            app.close()

    async def test_default_session_seeds_title_from_first_message(
        self, tmp_path, agent_replies, settle
    ) -> None:
        app = _app(tmp_path, FakeLLM(default="Got it."))
        try:
            await app.master.handle_user_message("帮我整理这批笔记")
            await settle(app)
            rows = app.master.sessions.list()
            assert rows and rows[0]["title"] == "帮我整理这批笔记"
        finally:
            app.close()

    async def test_replies_carry_session_field(self, tmp_path, agent_replies, settle) -> None:
        app = _app(tmp_path, FakeLLM(default="Got it."))
        try:
            await app.master.handle_user_message("你好", session_id="sess-x")
            await settle(app)
            events = [e for _, e in app.log.read_after(types=[DomainEvent.AGENT_MESSAGE])]
            assert events and all(e.payload.get("session") == "sess-x" for e in events)
        finally:
            app.close()

    async def test_invalid_session_id_gets_readable_reply(
        self, tmp_path, agent_replies, settle
    ) -> None:
        """A malformed session id never loses the message silently: the user
        gets a readable rejection instead of a stranded turn."""
        app = _app(tmp_path, FakeLLM(default="Got it."))
        try:
            await app.master.handle_user_message("hi", session_id="../evil")
            await settle(app)
            replies = agent_replies(app)
            assert replies and "无法创建会话" in replies[-1]
            assert all(r["session_id"] != "../evil" for r in app.master.sessions.list())
        finally:
            app.close()

    def test_rename_unknown_session_raises(self, tmp_path) -> None:
        app = _app(tmp_path, FakeLLM())
        try:
            with pytest.raises(ServiceError):
                app.master.sessions.rename("nope123", "x")
        finally:
            app.close()
