"""Tests for audit persistence: SqliteAuditSink directly, and wired into
execute()'s guard chain.
"""

import pytest
from platform_actor import ActorContext
from platform_capability import Registry, SqliteAuditSink, capability, execute
from platform_contracts import LOCAL_USER

_NOW = 1_000_000.0


def _entry(
    *,
    capability: str = "notes.create_note",
    trace_id: str = "tr1",
    ts: float = _NOW,
):
    from platform_capability import AuditEntry

    return AuditEntry(
        actor_id="u1",
        actor_kind="user",
        capability=capability,
        args_summary="{}",
        ok=True,
        error_code="",
        trace_id=trace_id,
        ts=ts,
    )


@pytest.fixture()
def sink(tmp_path):
    s = SqliteAuditSink(tmp_path / "audit.db")
    yield s
    s.close()


class TestSink:
    def test_record_and_recent(self, sink) -> None:
        from platform_capability import AuditEntry

        sink.record(
            AuditEntry(
                actor_id="u1",
                actor_kind="user",
                capability="notes.create_note",
                args_summary="{'title': 't'}",
                ok=True,
                error_code="",
                trace_id="tr1",
            )
        )
        sink.record(
            AuditEntry(
                actor_id="a1",
                actor_kind="agent",
                capability="graph.set_node",
                args_summary="{}",
                ok=False,
                error_code="GRAPH.INVALID_INPUT",
                trace_id="tr1",
            )
        )
        rows = sink.recent()
        assert [r["capability"] for r in rows] == ["graph.set_node", "notes.create_note"]
        assert rows[0]["ok"] is False and rows[0]["error_code"] == "GRAPH.INVALID_INPUT"
        assert len(sink.recent(trace_id="tr1")) == 2
        assert len(sink.recent(ok=True)) == 1
        assert len(sink.recent(capability="notes.create_note")) == 1

    def test_purge_older_than_days_keeps_recent(self, sink) -> None:
        sink.record(_entry(capability="old.cap", trace_id="old"))
        sink.record(_entry(capability="fresh.cap", ts=_NOW + 1, trace_id="fresh"))
        # 89 days before the newest row: inside the window
        purged = sink.purge_older_than_days(90, now=_NOW + 1)
        assert purged == 0
        assert len(sink.recent()) == 2
        # exactly 90 days after the newest row: the cutoff lands on its ts and
        # the strict-less comparison keeps it while the 1s-older row crosses
        purged = sink.purge_older_than_days(90, now=_NOW + 1 + 90 * 86400)
        assert purged == 1
        rows = sink.recent()
        assert [r["capability"] for r in rows] == ["fresh.cap"]


class TestGuardIntegration:
    async def test_execute_writes_audit(self, tmp_path) -> None:
        """With execute(audit=[sink]), both success and failure paths are audited."""
        s = SqliteAuditSink(tmp_path / "audit.db")
        reg = Registry("t")

        @capability(reg, name="ok_cap", description="ok")
        def ok_cap() -> dict:
            return {"ok": True}

        @capability(reg, name="boom", description="fail")
        def boom() -> dict:
            raise ValueError("explode")

        ctx = ActorContext(actor=LOCAL_USER, trace_id="trace-9")
        await execute(reg, "ok_cap", ctx, {}, audit=[s])
        with pytest.raises(ValueError):
            await execute(reg, "boom", ctx, {}, audit=[s])
        rows = s.recent(trace_id="trace-9")
        assert [r["capability"] for r in rows] == ["boom", "ok_cap"]
        assert rows[0]["ok"] is False
        s.close()
