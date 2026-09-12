"""Tests for the contracts package: event envelope, error codes, HTTP mapping."""

from platform_contracts import (
    HTTP_STATUS,
    LOCAL_USER,
    ActorKind,
    ActorRef,
    DomainEvent,
    ErrorSuffix,
    Event,
    HealthReport,
    HealthStatus,
    JobRef,
    JobStatus,
    ServiceError,
    make_code,
)


class TestEvent:
    def test_roundtrip(self) -> None:
        ev = Event(
            type=DomainEvent.USER_MESSAGE,
            actor=LOCAL_USER,
            payload={"text": "hello"},
        )
        restored = Event.from_dict(ev.to_dict())
        assert restored == ev
        assert restored.actor.kind is ActorKind.USER

    def test_envelope_fields(self) -> None:
        ev = Event(type="task.progress", actor=LOCAL_USER, payload={})
        d = ev.to_dict()
        assert set(d) == {"id", "type", "actor", "payload", "ts", "trace_id"}
        assert isinstance(d["ts"], float)

    def test_local_user_constant(self) -> None:
        assert LOCAL_USER == ActorRef(kind=ActorKind.USER, id="local")


class TestErrors:
    def test_make_code(self) -> None:
        assert make_code("graph", ErrorSuffix.UNAVAILABLE) == "GRAPH.UNAVAILABLE"
        assert make_code("code-exec", ErrorSuffix.QUEUE_FULL) == "CODE_EXEC.QUEUE_FULL"

    def test_http_mapping(self) -> None:
        assert HTTP_STATUS[ErrorSuffix.UNAVAILABLE] == 503
        assert HTTP_STATUS[ErrorSuffix.AUTH_REQUIRED] == 401
        assert HTTP_STATUS[ErrorSuffix.INVALID_INPUT] == 400

    def test_service_error_envelope(self) -> None:
        err = ServiceError(
            "graph",
            ErrorSuffix.UNAVAILABLE,
            "graph service unavailable",
            hint="retry later",
            trace_id="t1",
        )
        env = err.to_envelope()
        assert set(env) == {"error"}
        assert set(env["error"]) == {"code", "message", "service", "hint", "trace_id"}
        assert env["error"]["code"] == "GRAPH.UNAVAILABLE"
        assert err.http_status == 503


class TestDto:
    def test_job_ref(self) -> None:
        ref = JobRef(job_id="j1")
        assert ref.to_dict() == {"job_id": "j1", "status": "queued"}
        assert ref.status is JobStatus.QUEUED

    def test_health_report(self) -> None:
        rep = HealthReport(service="graph", status=HealthStatus.DOWN, detail="connection refused")
        assert rep.to_dict()["status"] == "down"
