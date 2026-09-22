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
