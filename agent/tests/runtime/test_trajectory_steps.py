"""Trajectory steps projection: the run_id-keyed read (TrajectoryStore.run_steps)
backing the gateway's /api/chat/trajectory?run_id mode - the subagent
execution view's data source - and the run rows it reports alongside.
"""

import time
from dataclasses import replace

from agent.runtime.trajectory import TrajectoryStore
from platform_contracts import ActorKind, ActorRef, DomainEvent, Event, RuntimeEvent
from platform_eventbus import EventLog

_AGENT = ActorRef(kind=ActorKind.AGENT, id="agent.main")


def _store(tmp_path) -> tuple[TrajectoryStore, EventLog]:
    log = EventLog(tmp_path / "events.db")
    return TrajectoryStore(tmp_path / "trajectory.db", log), log


def _step(run_id: str, name: str, session: str = "s1") -> Event:
    return Event(
        type=DomainEvent.AGENT_STEP,
        actor=_AGENT,
        payload={
            "run_id": run_id,
            "session": session,
            "subagent": "recon",
            "kind": "tool",
            "name": name,
            "summary": name,
            "detail": {},
        },
    )


class TestRunStepsProjection:
    def test_run_steps_returns_one_runs_rows_ascending(self, tmp_path) -> None:
        """Only the requested run's step rows come back (interleaved rows of
        other runs stay out), ascending by seq, in event-dict shape."""
        store, log = _store(tmp_path)
        for ev in (_step("r1", "a"), _step("r2", "b"), _step("r1", "c")):
            log.append(ev)
        assert store.catch_up() == 3
        rows = store.run_steps("r1")
        assert [(r["seq"], r["payload"]["name"]) for r in rows] == [(1, "a"), (3, "c")]
        assert all(r["type"] == DomainEvent.AGENT_STEP for r in rows)
        assert all(r["payload"]["run_id"] == "r1" for r in rows)
        store.close()
        log.close()

    def test_run_steps_limit_keeps_newest_window_ascending(self, tmp_path) -> None:
        """limit bounds the read to the NEWEST rows, still ascending — the
        newest-window direction the gateway's non-pageable run_id mode
        relies on; limit=None (the default) stays unbounded."""
        store, log = _store(tmp_path)
        for i in range(5):
            log.append(_step("r1", f"s{i}"))
        store.catch_up()
        rows = store.run_steps("r1", limit=2)
        assert [r["payload"]["name"] for r in rows] == ["s3", "s4"]
        assert len(store.run_steps("r1")) == 5
        store.close()
        log.close()

    def test_unknown_run_has_no_rows_and_runs_table_tracks_lifecycle(self, tmp_path) -> None:
        """An unknown run_id reads empty; the runs table reflects lifecycle
        events (run.failed -> status 'failed'), the list the panel polls."""
        store, log = _store(tmp_path)
        log.append(_step("r1", "a"))
        log.append(
            Event(
                type=RuntimeEvent.RUN_STARTED,
                actor=_AGENT,
                payload={"run_id": "r1", "subagent": "recon"},
            )
        )
        log.append(
            Event(
                type=RuntimeEvent.RUN_FAILED,
                actor=_AGENT,
                payload={"run_id": "r1", "error": "boom"},
            )
        )
        store.catch_up()
        assert store.run_steps("missing") == []
        runs = {r["run_id"]: r["status"] for r in store.list_runs()}
        assert runs.get("r1") == "failed"
        store.close()
        log.close()


class TestStepsPage:
    def test_default_newest_window_ascending_with_has_more(self, tmp_path) -> None:
        store, log = _store(tmp_path)
        for i in range(5):
            log.append(_step("r1", f"s{i}"))
        store.catch_up()
        rows, has_more = store.steps_page(limit=3)
        assert has_more is True and [r["payload"]["name"] for r in rows] == ["s2", "s3", "s4"]
        rows, has_more = store.steps_page(limit=4)
        assert has_more is True and [r["payload"]["name"] for r in rows] == ["s1", "s2", "s3", "s4"]
        store.close()
        log.close()

    def test_forward_paging_from_after_seq(self, tmp_path) -> None:
        store, log = _store(tmp_path)
        for i in range(4):
            log.append(_step("r1", f"s{i}"))
        store.catch_up()
        rows, has_more = store.steps_page(after_seq=2, limit=10)
        assert has_more is False and [r["payload"]["name"] for r in rows] == ["s2", "s3"]
        store.close()
        log.close()

    def test_backward_paging_before_seq(self, tmp_path) -> None:
        store, log = _store(tmp_path)
        for i in range(5):
            log.append(_step("r1", f"s{i}"))
        store.catch_up()
        rows, _has_more = store.steps_page(before_seq=4, limit=2)
        assert [r["payload"]["name"] for r in rows] == ["s1", "s2"]  # window, oldest first
        store.close()
        log.close()

    def test_session_filter_and_limit_floor(self, tmp_path) -> None:
        store, log = _store(tmp_path)
        log.append(_step("r1", "a", session="s1"))
        log.append(_step("r2", "b", session="s2"))
        store.catch_up()
        rows, _ = store.steps_page(session="s1", limit=0)
        assert [r["payload"]["name"] for r in rows] == ["a"]
        assert rows[0]["payload"]["session"] == "s1"
        store.close()
        log.close()


class TestRunLifecycle:
    def test_run_started_keeps_original_started_ts_on_replay(self, tmp_path) -> None:
        store, log = _store(tmp_path)
        log.append(Event(type=RuntimeEvent.RUN_STARTED, actor=_AGENT, payload={"run_id": "r1"}))
        log.append(Event(type=RuntimeEvent.RUN_STARTED, actor=_AGENT, payload={"run_id": "r1"}))
        store.catch_up()
        (run,) = store.list_runs()
        assert run["status"] == "running"
        store.close()
        log.close()

    def test_cancellation_events_map_to_cancelled(self, tmp_path) -> None:
        store, log = _store(tmp_path)
        log.append(Event(type=RuntimeEvent.RUN_CANCELLED, actor=_AGENT, payload={"run_id": "r1"}))
        log.append(Event(type=RuntimeEvent.AGENT_CANCELLED, actor=_AGENT, payload={"run_id": "r2"}))
        store.catch_up()
        runs = {r["run_id"]: r["status"] for r in store.list_runs()}
        assert runs == {"r1": "cancelled", "r2": "cancelled"}
        store.close()
        log.close()

    def test_lifecycle_event_without_run_id_is_ignored(self, tmp_path) -> None:
        store, log = _store(tmp_path)
        log.append(Event(type=RuntimeEvent.RUN_STARTED, actor=_AGENT, payload={}))
        log.append(Event(type=RuntimeEvent.RUN_FAILED, actor=_AGENT, payload={}))
        store.catch_up()
        assert store.list_runs() == []
        store.close()
        log.close()

    def test_step_without_run_id_still_lands_but_creates_no_run(self, tmp_path) -> None:
        store, log = _store(tmp_path)
        log.append(
            Event(
                type=DomainEvent.AGENT_STEP,
                actor=_AGENT,
                payload={"kind": "llm", "name": "think", "summary": "s"},
            )
        )
        store.catch_up()
        assert store.run_steps("missing") == []
        rows, _ = store.steps_page()
        assert len(rows) == 1  # the step row exists keyed by seq alone
        assert store.list_runs() == []  # no run row without a run_id
        store.close()
        log.close()

    def test_run_rows_carry_step_tool_and_token_accounting(self, tmp_path) -> None:
        store, log = _store(tmp_path)
        log.append(_step("r1", "think"))  # kind tool -> tool_calls +1
        log.append(_step("r1", "read"))
        store.catch_up()
        (run,) = store.list_runs()
        assert run["steps"] == 2 and run["tool_calls"] == 2
        assert run["session"] == "s1" and run["subagent"] == "recon"
        store.close()
        log.close()


class TestCatchUpSemantics:
    def test_catch_up_after_close_is_a_no_op(self, tmp_path) -> None:
        store, log = _store(tmp_path)
        log.append(_step("r1", "a"))
        store.catch_up()
        store.close()
        assert store.catch_up() == 0  # closed: never touches the log again
        log.close()

    def test_repeated_catch_up_is_idempotent(self, tmp_path) -> None:
        store, log = _store(tmp_path)
        log.append(_step("r1", "a"))
        assert store.catch_up() == 1
        assert store.catch_up() == 0
        assert len(store.run_steps("r1")) == 1
        store.close()
        log.close()

    def test_list_runs_filters_by_session(self, tmp_path) -> None:
        store, log = _store(tmp_path)
        log.append(_step("r1", "a", session="s1"))
        log.append(_step("r2", "b", session="s2"))
        store.catch_up()
        assert [r["run_id"] for r in store.list_runs(session="s2")] == ["r2"]
        assert len(store.list_runs()) == 2
        store.close()
        log.close()


class TestStepsRetention:
    """Startup retention (purge_steps_older_than_days): step rows past the
    cutoff go, TERMINAL runs rows (ended_ts set) past the cutoff go with
    them, and a run that never ended (ended_ts = 0: alive / paused) keeps
    its runs row so it stays listed and resumable."""

    @staticmethod
    def _terminal(ev_type: str, run_id: str, ts: float) -> Event:
        return replace(
            Event(
                type=ev_type,
                actor=_AGENT,
                payload={"run_id": run_id, "error": "boom"},
            ),
            ts=ts,
        )

    def _runs_row(self, store: TrajectoryStore, run_id: str) -> tuple[float, str] | None:
        with store._lock:
            row = store._conn.execute(
                "SELECT ended_ts, status FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return (row[0], row[1]) if row else None

    def test_old_terminal_run_steps_and_runs_rows_are_purged(self, tmp_path) -> None:
        old = time.time() - 30 * 86400
        store, log = _store(tmp_path)
        log.append(replace(_step("old", "a"), ts=old))
        log.append(replace(_step("old", "b"), ts=old))
        log.append(self._terminal(RuntimeEvent.RUN_FAILED, "old", old))
        log.append(replace(_step("new", "a"), ts=time.time()))
        log.append(self._terminal(RuntimeEvent.AGENT_COMPLETED, "new", time.time()))
        store.catch_up()
        # the return value counts STEP rows (2), not the also-deleted runs row
        assert store.purge_steps_older_than_days(7) == 2
        assert store.run_steps("old") == []
        assert self._runs_row(store, "old") is None
        assert [r["payload"]["name"] for r in store.run_steps("new")] == ["a"]
        new_row = self._runs_row(store, "new")
        assert new_row is not None and new_row[1] == "completed"
        store.close()
        log.close()

    def test_unended_run_keeps_its_runs_row(self, tmp_path) -> None:
        """A run without a terminal event (ended_ts = 0: alive / paused)
        keeps its runs row even when every other timestamp is past the
        cutoff — it must stay listed and resumable; its old step rows still
        go (the step purge filters by ts only)."""
        old = time.time() - 30 * 86400
        store, log = _store(tmp_path)
        log.append(replace(_step("alive", "a"), ts=old))
        log.append(replace(_step("alive", "b"), ts=old))
        store.catch_up()
        assert store.purge_steps_older_than_days(7) == 2
        assert store.run_steps("alive") == []
        row = self._runs_row(store, "alive")
        assert row is not None and row[0] == 0.0
        store.close()
        log.close()

    def test_nonpositive_days_is_a_no_op(self, tmp_path) -> None:
        store, log = _store(tmp_path)
        log.append(replace(_step("r", "a"), ts=time.time() - 30 * 86400))
        store.catch_up()
        assert store.purge_steps_older_than_days(0) == 0
        assert store.purge_steps_older_than_days(-1) == 0
        assert [r["payload"]["name"] for r in store.run_steps("r")] == ["a"]
        store.close()
        log.close()
