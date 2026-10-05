"""Audit persistence: a SQLite-backed AuditSink.

guards.InMemoryAuditSink is the development/test placeholder; production
wires this sink at the composition root by default, so audits survive
restarts and can be queried by trace_id, time, or capability name. Writes
are synchronous single-row sqlite inserts (microsecond scale) and do not
slow the capability call path.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Self

from platform_contracts import retention_cutoff

from platform_capability.guards import AuditEntry

#: Audit rows are an operational history (who called what, with what
#: outcome), not an archive: every capability call writes one row, so
#: without a policy the table grows forever (45MB was observed). Purged at
#: sink construction (process startup) by ts; 90 days mirrors meter.db.
AUDIT_RETENTION_DAYS = 90

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           REAL NOT NULL,
    actor_id     TEXT NOT NULL,
    actor_kind   TEXT NOT NULL,
    capability   TEXT NOT NULL,
    args_summary TEXT NOT NULL,
    ok           INTEGER NOT NULL,
    error_code   TEXT NOT NULL DEFAULT '',
    trace_id     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit(ts);
CREATE INDEX IF NOT EXISTS idx_audit_trace ON audit(trace_id);
CREATE INDEX IF NOT EXISTS idx_audit_capability ON audit(capability);
"""

_COLS = (
    "id",
    "ts",
    "actor_id",
    "actor_kind",
    "capability",
    "args_summary",
    "ok",
    "error_code",
    "trace_id",
)

# Plain-literal SELECT head; the column list is kept in lockstep with _COLS
# (which feeds dict(zip()) below), never widened to *. Filter conditions are
# appended dynamically as literal fragments with bound parameters.
_SQL_RECENT_HEAD = (
    "SELECT id, ts, actor_id, actor_kind, capability, args_summary, ok,"
    " error_code, trace_id FROM audit"
)


class SqliteAuditSink:
    """Audit ingestion: the guard chain records on every outcome; single
    connection serialized by one shared read/write lock."""

    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()
        # Startup purge of audit rows past the retention window; freed pages
        # are reused by later inserts (no VACUUM: too heavy for startup).
        self.purge_older_than_days(AUDIT_RETENTION_DAYS)

    def record(self, entry: AuditEntry) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit (ts, actor_id, actor_kind, capability,"
                " args_summary, ok, error_code, trace_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.ts,
                    entry.actor_id,
                    entry.actor_kind,
                    entry.capability,
                    entry.args_summary,
                    int(entry.ok),
                    entry.error_code,
                    entry.trace_id,
                ),
            )
            self._conn.commit()

    def recent(
        self, *, limit: int = 100, capability: str = "", trace_id: str = "", ok: bool | None = None
    ) -> list[dict[str, Any]]:
        """Query audits: newest first, filterable by capability/trace/outcome.

        No query endpoint is wired yet — production is currently write-only
        (the activity page reads the event stream for now); this interface is
        reserved for debugging and the activity page's operation-history view.
        """
        sql = _SQL_RECENT_HEAD
        conds: list[str] = []
        params: list[Any] = []
        if capability:
            conds.append("capability = ?")
            params.append(capability)
        if trace_id:
            conds.append("trace_id = ?")
            params.append(trace_id)
        if ok is not None:
            conds.append("ok = ?")
            params.append(int(ok))
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        out = [dict(zip(_COLS, r)) for r in rows]
        for item in out:
            item["ok"] = bool(item["ok"])
        return out

    def purge_older_than_days(self, days: int, *, now: float | None = None) -> int:
        """Delete audit rows older than now - days (strictly less), returning
        the row count. Startup-time maintenance over the ts index."""
        cutoff = retention_cutoff(days, now=now)
        with self._lock:
            cur = self._conn.execute("DELETE FROM audit WHERE ts < ?", (cutoff,))
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
