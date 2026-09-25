"""Raw LLM round log: TrajectoryStore raw_rounds round-trip and the REACT
on_raw wiring (one full request transcript + response per round)."""

from typing import Any, cast

from agent.engine import Mode, ModeLimits, run_mode
from agent.llm import FakeLLM, LLMReply, ToolSpec
from agent.policy import PolicyEngine
from agent.runtime.trajectory import TrajectoryStore
from agent.tools import AgentTool, Toolbelt
from platform_eventbus import EventBus, EventLog


def _store(tmp_path) -> TrajectoryStore:
    return TrajectoryStore(tmp_path / "trajectory.db", EventLog(tmp_path / "events.db"))


def _msgs() -> list[dict]:
    return [{"role": "user", "content": "任务"}]


def _belt() -> Toolbelt:
    async def echo_tool(x: str = "") -> str:
        return f"echo:{x}"

    return Toolbelt(
        {"echo_tool": AgentTool(name="echo_tool", description="测试工具", handler=echo_tool)},
        PolicyEngine(),
    )


class TestRawRoundsTable:
    def test_round_trip(self, tmp_path) -> None:
        store = _store(tmp_path)
        store.record_raw_round(run_id="r1", session="chat", round=1, request="[]", response="{}")
        store.record_raw_round(run_id="r1", session="chat", round=2, request="[a]", response="[b]")
        rounds = store.raw_rounds("r1")
        assert [r["round"] for r in rounds] == [1, 2]
        assert rounds[0]["request_bytes"] == 2
        full = store.raw_round("r1", 2)
        assert full is not None and full["response"] == "[b]"
        assert store.raw_round("r1", 9) is None
        assert store.raw_rounds("missing") == []
        store.close()

    def test_overwrite_same_round_and_cap(self, tmp_path) -> None:
        store = _store(tmp_path)
        store.record_raw_round(run_id="r", session="", round=1, request="first", response="x")
        store.record_raw_round(run_id="r", session="", round=1, request="second", response="y")
        full = store.raw_round("r", 1)
        assert full is not None and full["request"] == "second"
        store.close()


class TestSessionGlobalNumbering:
    def test_seq_round_continues_across_run_ids(self, tmp_path) -> None:
        """Display numbering is session-global: a second run_id in the same
        session (new process / new run) continues after the first's rounds
        instead of restarting at 1."""
        store = _store(tmp_path)
        store.record_raw_round(run_id="r1", session="chat", round=1, request="a", response="a")
        store.record_raw_round(run_id="r1", session="chat", round=2, request="b", response="b")
        store.record_raw_round(run_id="r2", session="chat", round=1, request="c", response="c")
        rounds, total = store.raw_rounds_for_session("chat", limit=10)
        assert total == 3
        assert [r["round"] for r in rounds] == [1, 2, 3]
        store.close()

    def test_seq_round_is_per_session(self, tmp_path) -> None:
        store = _store(tmp_path)
        store.record_raw_round(run_id="r1", session="s1", round=1, request="a", response="a")
        store.record_raw_round(run_id="r2", session="s2", round=1, request="b", response="b")
        s1, _ = store.raw_rounds_for_session("s1", limit=10)
        s2, _ = store.raw_rounds_for_session("s2", limit=10)
        assert [r["round"] for r in s1] == [1]
        assert [r["round"] for r in s2] == [1]
        store.close()

    def test_wire_request_round_trip(self, tmp_path) -> None:
        store = _store(tmp_path)
        store.record_raw_round(
            run_id="r",
            session="chat",
            round=1,
            request="[]",
            response="{}",
            wire_request='{"stream": true}',
        )
        rounds, _ = store.raw_rounds_for_session("chat", limit=10)
        assert rounds[0]["wire_request"] == '{"stream": true}'
        full = store.raw_round("r", 1)
        assert full is not None and full["wire_request"] == '{"stream": true}'
        # absent wire_request -> empty string, not an error
        store.record_raw_round(run_id="r2", session="chat", round=1, request="x", response="y")
        rounds2, _ = store.raw_rounds_for_session("chat", limit=10)
        assert [r["wire_request"] for r in rounds2] == ['{"stream": true}', ""]
        store.close()

    def test_migration_backfills_by_ts_not_row_order(self, tmp_path) -> None:
        """Legacy rows (seq_round=0) written out of ts order get renumbered
        by ts — the single UPDATE would see its own partial writes and number
        by scan order instead, so this locks the Python-side renumber."""
        import sqlite3

        db = tmp_path / "trajectory.db"
        store = _store(tmp_path)
        conn = sqlite3.connect(db)
        # (run_id, round, session, ts, request, response, seq_round, wire_request)
        # ts order: run2/1 < run1/1 < run1/2 < run2/2; insert order differs.
        conn.execute("INSERT INTO raw_rounds VALUES ('run2',1,'chat',99.0,'','',0,'')")
        conn.execute("INSERT INTO raw_rounds VALUES ('run1',1,'chat',100.0,'','',0,'')")
        conn.execute("INSERT INTO raw_rounds VALUES ('run1',2,'chat',101.0,'','',0,'')")
        conn.execute("INSERT INTO raw_rounds VALUES ('run2',2,'chat',102.0,'','',0,'')")
        conn.commit()
        conn.close()
        store.close()  # reopen: __init__ runs the backfill
        store2 = TrajectoryStore(db, EventLog(tmp_path / "events.db"))
        rows = store2._conn.execute(
            "SELECT run_id, round, seq_round FROM raw_rounds ORDER BY ts"
        ).fetchall()
        assert [r[2] for r in rows] == [1, 2, 3, 4]
        # second open: idempotent (no seq_round=0 rows left)
        store2.close()
        store3 = TrajectoryStore(db, EventLog(tmp_path / "events.db"))
        rows2 = store3._conn.execute(
            "SELECT run_id, round, seq_round FROM raw_rounds ORDER BY ts"
        ).fetchall()
        assert rows == rows2
        store3.close()

    def test_backfill_continues_after_post_migration_rows(self, tmp_path) -> None:
        """Rows already numbered (written post-migration) keep their numbers;
        the backfill of legacy rows continues after the session's max (even
        when the legacy ts is older — renumbering already-shown numbers would
        collide with the runtime MAX+1 allocator)."""
        import sqlite3

        db = tmp_path / "trajectory.db"
        store = _store(tmp_path)
        store.record_raw_round(run_id="new", session="chat", round=1, request="n", response="n")
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO raw_rounds VALUES ('old',1,'chat',50.0,'','',0,'')")
        conn.commit()
        conn.close()
        store.close()
        store2 = TrajectoryStore(db, EventLog(tmp_path / "events.db"))
        rows = store2._conn.execute(
            "SELECT run_id, seq_round FROM raw_rounds ORDER BY seq_round"
        ).fetchall()
        assert dict(rows) == {"new": 1, "old": 2}
        store2.close()


class TestRawRetentionAndPaging:
    def test_session_paging_returns_newest_window_with_total(self, tmp_path) -> None:
        store = _store(tmp_path)
        for i in range(5):
            store.record_raw_round(
                run_id="r", session="chat", round=i + 1, request=str(i), response=str(i)
            )
        rounds, total = store.raw_rounds_for_session("chat", limit=3)
        assert total == 5
        # newest window, returned oldest-first within the window
        assert [r["round"] for r in rounds] == [3, 4, 5]

    def test_purge_drops_only_rows_older_than_the_cutoff_days(self, tmp_path) -> None:
        import time

        store = _store(tmp_path)
        store.record_raw_round(run_id="old", session="", round=1, request="x", response="x")
        store.record_raw_round(run_id="new", session="", round=1, request="y", response="y")
        with store._lock:
            store._conn.execute(
                "UPDATE raw_rounds SET ts = ? WHERE run_id = 'old'", (time.time() - 30 * 86400,)
            )
            store._conn.commit()
        assert store.purge_raw_older_than_days(7) == 1
        assert store.raw_round("old", 1) is None
        assert store.raw_round("new", 1) is not None
        # non-positive retention disables the purge
        store.record_raw_round(run_id="keep", session="", round=1, request="z", response="z")
        assert store.purge_raw_older_than_days(0) == 0
        store.close()


class TestReactWiring:
    async def test_on_raw_receives_request_and_reply(self) -> None:
        llm = FakeLLM([LLMReply(text="完成")])
        captured: list[tuple[int, list, object]] = []

        async def on_raw(round_n: int, messages: list, reply: object) -> None:
            captured.append((round_n, messages, reply))

        messages = [{"role": "user", "content": "任务"}]
        await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=_belt(),
            messages=messages,
            limits=ModeLimits(),
            on_raw=on_raw,
        )
        assert len(captured) == 1
        round_n, req, reply = captured[0]
        assert round_n == 1 and req is messages
        assert getattr(reply, "text", "") == "完成"

    async def test_other_modes_do_not_receive_on_raw(self) -> None:
        """Non-REACT runners do not take the parameter: the dispatcher must
        not forward it (they never face the user)."""
        llm = FakeLLM([LLMReply(text="ok")])
        result = await run_mode(
            Mode.DIRECT, llm=llm, toolbelt=None, messages=_msgs(), limits=ModeLimits()
        )
        assert result == "ok"


class TestCrossTurnNumbering:
    class _CaptureBus:
        """Minimal EventBus stub: records published events (events uses publish only)."""

        def __init__(self, sink: list) -> None:
            self._sink = sink

        async def publish(self, event) -> int:
            self._sink.append(event)
            return len(self._sink)

    async def test_turns_continue_round_numbers_instead_of_resetting(self) -> None:
        """Conversational run_ids persist across turns while react renumbers
        rounds from 1 per turn; the instance must offset the second turn past
        the first, or INSERT OR REPLACE silently drops the earlier records."""
        from agent.engine.instance import SubagentInstance, TaskBook
        from agent.runtime.events import RuntimeEvents
        from agent.runtime.state import RunState

        llm = FakeLLM([LLMReply(text="answer one"), LLMReply(text="answer two")])
        captured: list[int] = []

        async def recorder(run_id: str, round_n: int, messages: list, reply: object) -> None:
            captured.append(round_n)

        inst = SubagentInstance(
            task=TaskBook(goal="goal", conversational=True),
            toolbelt=_belt(),
            llm=llm,
            system_prompt="sys",
            events=RuntimeEvents(cast(EventBus, self._CaptureBus([]))),
            state=RunState(task="goal"),
            raw_recorder=recorder,
        )
        # "ok" matches the chitchat fast path: one LLM round per turn
        await inst.run_turn("ok")
        await inst.run_turn("ok")
        assert captured == [1, 2]

    async def test_turn_stamps_the_capability_session_context(self) -> None:
        """Domain capabilities called mid-turn read the session from the
        capability invocation context; it must reset after the turn."""
        from agent.engine.instance import SubagentInstance, TaskBook
        from agent.runtime.events import RuntimeEvents
        from agent.runtime.state import RunState
        from platform_capability import current_chat_session

        seen: list[str] = []

        class ProbeLLM(FakeLLM):
            async def complete(
                self,
                messages: list[dict[str, Any]],
                tools: list[ToolSpec] | None = None,
                response_format: dict[str, Any] | None = None,
                max_tokens: int | None = None,
            ) -> LLMReply:
                seen.append(current_chat_session.get())
                return await super().complete(messages, tools)

        inst = SubagentInstance(
            task=TaskBook(goal="goal", conversational=True, session="sess-1"),
            toolbelt=_belt(),
            llm=ProbeLLM([LLMReply(text="ok")]),
            system_prompt="sys",
            events=RuntimeEvents(cast(EventBus, self._CaptureBus([]))),
            state=RunState(task="goal"),
        )
        await inst.run_turn("ok")
        assert seen == ["sess-1"]
        assert current_chat_session.get() == ""
