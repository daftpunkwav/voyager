"""Tests for health monitoring: transition events, probe exceptions as DOWN,
and error helpers.
"""

import pytest
from platform_contracts import DomainEvent, ErrorSuffix, HealthReport, HealthStatus
from platform_eventbus import EventBus, EventLog
from platform_health import HealthMonitor, queue_full, unavailable


@pytest.fixture()
def rig(tmp_path):
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    monitor = HealthMonitor(bus)
    yield monitor, log
    log.close()


class TestMonitor:
    async def test_first_observation_and_transition(self, rig) -> None:
        monitor, log = rig
        state = {"up": True}

        async def probe() -> HealthReport:
            return HealthReport(
                service="graph",
                status=HealthStatus.UP if state["up"] else HealthStatus.DOWN,
                detail="" if state["up"] else "connection refused",
            )

        monitor.register("graph", probe)
        await monitor.poll_once()
        assert monitor.status("graph") is HealthStatus.UP

        state["up"] = False
        await monitor.poll_once()
        assert monitor.status("graph") is HealthStatus.DOWN

        events = [e for _, e in log.read_after(types=[DomainEvent.SERVICE_HEALTH_CHANGED])]
        assert len(events) == 2  # unknown->up, up->down
        assert events[0].payload["from"] == "unknown"
        assert events[1].payload == {
            "service": "graph",
            "from": "up",
            "to": "down",
            "detail": "connection refused",
            "ts": events[1].payload["ts"],
        }
        assert events[1].actor.id == "platform.health"

    async def test_steady_state_no_duplicate_event(self, rig) -> None:
        monitor, log = rig
        monitor.register("notes", lambda: HealthReport("notes", HealthStatus.UP))
        await monitor.poll_once()
        await monitor.poll_once()
        events = log.read_after(types=[DomainEvent.SERVICE_HEALTH_CHANGED])
        assert len(events) == 1

    async def test_probe_exception_means_down(self, rig) -> None:
        monitor, _ = rig

        def boom() -> HealthReport:
            raise ConnectionRefusedError("refused")

        monitor.register("sources", boom)
        await monitor.poll_once()
        assert monitor.status("sources") is HealthStatus.DOWN
        assert "ConnectionRefusedError" in monitor.snapshot()["sources"]["detail"]

    async def test_unknown_service(self, rig) -> None:
        monitor, _ = rig
        assert monitor.status("ghost") is HealthStatus.UNKNOWN

    async def test_start_idempotent_and_stop_awaits(self) -> None:
        """start is reentrant-safe (no task leak); stop awaits actual task
        completion and start can be called again."""
        monitor = HealthMonitor()
        monitor.register("x", lambda: HealthReport(service="x", status=HealthStatus.UP))
        monitor.start(0.01)
        first = monitor._task
        assert first is not None
        monitor.start(0.01)  # reentrant: keeps the same task
        assert monitor._task is first
        await monitor.stop()
        assert monitor._task is None and first.done()
        monitor.start(0.01)  # restartable after stop
        await monitor.stop()


class TestErrorHelpers:
    def test_unavailable(self) -> None:
        err = unavailable("graph", trace_id="t1")
        assert err.body.code == "GRAPH.UNAVAILABLE"
        assert err.http_status == 503
        assert err.body.hint

    def test_queue_full(self) -> None:
        err = queue_full("code-exec")
        assert err.body.code == "CODE_EXEC.QUEUE_FULL"
        assert err.http_status == 429
        assert ErrorSuffix.QUEUE_FULL.value in err.body.code
