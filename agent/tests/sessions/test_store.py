"""Tests for multi-session persistence: keyed round-trip, active
pointer, legacy single-row migration, corrupt-row tolerance, and restart
survival through the session manager (lazy restore into a fresh process).
"""

from agent.llm import FakeLLM, LLMReply
from agent.main import build_agent
from agent.sessions.store import SessionSnapshot, SessionStore


def _snap(session_id="chat", **kw) -> SessionSnapshot:
    defaults = {
        "session_id": session_id,
        "title": "演示",
        "persona": "orchestrator",
        "goal": "chat",
        "history": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}],
        "active_tools": ["web_search", "read_file"],
    }
    defaults.update(kw)
    return SessionSnapshot(**defaults)


class TestStore:
    def test_round_trip(self, tmp_path) -> None:
        store = SessionStore(tmp_path / "sessions.db")
        store.save(_snap())
        loaded = store.get("chat")
        assert loaded is not None
        assert loaded.persona == "orchestrator"
        assert [m["content"] for m in loaded.history] == ["hi", "yo"]
        assert loaded.active_tools == ["web_search", "read_file"]
        store.close()

    def test_absent_returns_none(self, tmp_path) -> None:
        store = SessionStore(tmp_path / "sessions.db")
        assert store.get("chat") is None
        store.close()

    def test_corrupt_row_returns_none_and_listing_skips_it(self, tmp_path) -> None:
        store = SessionStore(tmp_path / "sessions.db")
        store.create("good", title="good")
        store._conn.execute("UPDATE sessions SET snapshot = 'not-json' WHERE id = 'good'")
        store._conn.commit()
        assert store.get("good") is None  # corrupt data never breaks startup
        # listings keep the row metadata (title survived) and never crash
        assert [r.session_id for r in store.list()] == ["good"]
        store.close()

    def test_multi_row_list_order_and_meta(self, tmp_path) -> None:
        store = SessionStore(tmp_path / "sessions.db")
        a = store.create("aaa", title="first")
        store.save(_snap("bbb", title="second"))
        rows = store.list()
        assert [r.session_id for r in rows] == ["bbb", "aaa"]  # newest first
        store.touch("aaa")
        assert store.list()[0].session_id == "aaa"
        assert a.title == "first"
        store.close()

    def test_active_pointer(self, tmp_path) -> None:
        store = SessionStore(tmp_path / "sessions.db")
        assert store.get_active() == ""
        store.create("s1", title="")
        store.set_active("s1")
        assert store.get_active() == "s1"
        store.delete("s1")
        store.set_active("")
        assert store.get_active() == ""
        store.close()

    def test_rename_and_delete(self, tmp_path) -> None:
        store = SessionStore(tmp_path / "sessions.db")
        store.create("s1", title="old")
        store.rename("s1", "new")
        snap = store.get("s1")
        assert snap is not None
        assert snap.title == "new"
        assert snap.history == []
        store.delete("s1")
        assert store.get("s1") is None
        store.close()

    def test_set_flags_and_rename_preserve_curation(self, tmp_path) -> None:
        """Flagging keeps updated_at (not conversation activity); renaming
        keeps the flags (a rename must not silently unpin the session)."""
        store = SessionStore(tmp_path / "sessions.db")
        store.create("s1", title="old")
        before = store.get("s1")
        assert before is not None
        snap = store.set_flags("s1", pinned=True, archived=True)
        assert snap is not None
        assert snap.pinned and snap.archived
        assert snap.updated_at == before.updated_at
        assert store.list()[0].session_id == "s1"  # pinned sorts first
        store.rename("s1", "renamed")
        renamed = store.get("s1")
        assert renamed is not None
        assert renamed.title == "renamed"
        assert renamed.pinned and renamed.archived
        store.close()

    def test_invalid_session_id_rejected(self, tmp_path) -> None:
        store = SessionStore(tmp_path / "sessions.db")
        for bad in ("", "../evil", "a" * 100, "has space"):
            try:
                store.create(bad, title="")
            except ValueError:
                continue
            raise AssertionError(f"invalid id accepted: {bad!r}")
        store.close()

    def test_legacy_single_row_migrates(self, tmp_path) -> None:
        """The pre-multi-session store kept one row in `session` (key=chat);
        opening the store copies it into a real session and points active at it."""
        import json
        import sqlite3

        db = tmp_path / "sessions.db"
        legacy = sqlite3.connect(db)
        legacy.execute(
            "CREATE TABLE session (key TEXT PRIMARY KEY, value TEXT NOT NULL, saved_at TEXT NOT NULL)"
        )
        legacy.execute(
            "INSERT INTO session (key, value, saved_at) VALUES ('chat', ?, 'x')",
            (
                json.dumps(
                    {
                        "persona": "orchestrator",
                        "goal": "chat",
                        "history": [{"role": "user", "content": "旧对话"}],
                        "active_tools": ["read_file"],
                    }
                ),
            ),
        )
        legacy.commit()
        legacy.close()

        store = SessionStore(db)
        snap = store.get("chat")
        assert snap is not None
        assert [m["content"] for m in snap.history] == ["旧对话"]
        assert snap.active_tools == ["read_file"]
        assert store.get_active() == "chat"
        # The legacy table is left in place (read-only after migration)
        rows = store._conn.execute("SELECT key FROM session").fetchall()
        assert rows == [("chat",)]
        store.close()


class TestRestartSurvival:
    async def test_history_restored_into_fresh_app(self, tmp_path, agent_replies, settle) -> None:
        """Turn 1 in app #1 persists; app #2 (same data dir) lazily restores
        the session so the model still sees the earlier conversation."""
        llm_script = [LLMReply(text="first answer"), LLMReply(text="second answer")]

        data_dir = tmp_path / "rd"
        ws = tmp_path / "ws"
        app1 = build_agent(
            data_dir=data_dir,
            workspace_dir=ws,
            llm=FakeLLM([llm_script[0]]),
        )
        try:
            await app1.master.handle_user_message("记住暗号是 pineapple")
            await settle(app1)
            assert agent_replies(app1) == ["first answer"]
        finally:
            app1.close()

        fake2 = FakeLLM([llm_script[1]])
        app2 = build_agent(
            data_dir=data_dir,
            workspace_dir=ws,
            llm=fake2,
        )
        try:
            await app2.master.handle_user_message("暗号是什么?")
            await settle(app2)
            chat = app2.master.chat
            assert chat is not None
            roles = [m["role"] for m in chat.history]
            assert roles.count("user") >= 2  # the pre-restart turn is present
            assert any("pineapple" in str(m.get("content")) for m in chat.history)
            # the model saw the restored history on the post-restart turn
            sent = fake2.calls[-1]["messages"]
            assert any("pineapple" in str(m.get("content")) for m in sent)
        finally:
            app2.close()

    async def test_chat_turn_without_store(self, tmp_path, agent_replies, settle) -> None:
        """Without a store (legacy wiring passes None) chat still works:
        restore and persistence are skipped, nothing crashes."""
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM([LLMReply(text="ok")]),
        )
        try:
            app.master.sessions._store = None  # simulate legacy wiring
            app.master.sessions._active = ""
            await app.master.handle_user_message("hi")
            await settle(app)
            assert agent_replies(app) == ["ok"]
        finally:
            app.close()
