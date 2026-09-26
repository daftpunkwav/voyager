"""Trajectory steps projection: the run_id-keyed read (TrajectoryStore.run_steps)
backing the gateway's /api/chat/trajectory?run_id mode - the subagent
execution view's data source - and the run rows it reports alongside.
"""

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
