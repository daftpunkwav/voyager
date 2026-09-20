"""Jobs projection + cancellation routing."""

from __future__ import annotations

import asyncio

from agent.build import build_agent
from agent.llm import FakeLLM
from agent.runtime.jobs_view import JobsView
from platform_contracts import ActorKind, ActorRef, DomainEvent, Event
from platform_eventbus import EventLog

_SYSTEM = ActorRef(kind=ActorKind.SYSTEM, id="test")


def _view_with_events(tmp_path):
    log = EventLog(tmp_path / "events.db")

    def emit(seq_payload: dict, etype: str):
        log.append(Event(type=etype, actor=_SYSTEM, payload=seq_payload))

    emit(
        {"job_id": "j-1", "kind": "index", "title": "import repo", "source": "graph"},
        DomainEvent.TASK_ENQUEUED,
    )
    emit({"job_id": "j-1", "kind": "index"}, DomainEvent.TASK_PROGRESS)
    emit(
        {"job_id": "j-2", "kind": "index", "title": "other", "source": "graph", "error": "x"},
        DomainEvent.TASK_FAILED,
    )
    return JobsView(log), log


class TestJobsView:
    def test_latest_status_wins(self, tmp_path) -> None:
        view, log = _view_with_events(tmp_path)
        rows = view.list_jobs()
        assert [r["job_id"] for r in rows] == ["j-2", "j-1"]  # newest first
        assert rows[1]["status"] == "running" and rows[1]["title"] == "import repo"
        assert rows[0]["status"] == "failed"
        assert view.find("j-1") is not None and view.find("nope") is None
        log.close()


class TestQueueStartWiring:
    async def test_agentapp_starts_queue_loop(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            ran: list[str] = []

            async def handler(payload: dict) -> None:
                ran.append(payload["n"])

            app.scheduler.register_job_handler("t", handler)
            app.queue_store.enqueue(kind="t", payload={"n": 1}, delay_s=0)
            await app.start_queue_loop(poll_interval=0.05)
            for _ in range(60):
                if ran:
                    break
                await asyncio.sleep(0.05)
            assert ran == [1]
        finally:
            await app.scheduler.stop_queue()
            app.close()
