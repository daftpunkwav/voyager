"""Trajectory projection: a query index over the event stream (source of
truth stays the event log, D-07).

One writer only: `catch_up()` reads the log from the projection's own
cursor and folds agent.step rows plus run lifecycle events into two tables
(steps / runs). Seq numbers are the log's, so paging cursors handed to the
chat UI keep their meaning; re-running catch_up is idempotent (INSERT OR
IGNORE by seq, cursor persisted in meta) and a deleted trajectory.db simply
rebuilds from the log. Reads never touch the log.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from platform_contracts import DomainEvent, Event, RuntimeEvent
from platform_eventbus import EventLog

_SCHEMA = """
CREATE TABLE IF NOT EXISTS steps (
    seq      INTEGER PRIMARY KEY,
    run_id   TEXT NOT NULL DEFAULT '',
    session  TEXT NOT NULL DEFAULT '',
    subagent TEXT NOT NULL DEFAULT '',
    ts       REAL NOT NULL,
    trace_id TEXT NOT NULL DEFAULT '',
    actor    TEXT NOT NULL DEFAULT '{}',
    kind     TEXT NOT NULL DEFAULT '',
    name     TEXT NOT NULL DEFAULT '',
    summary  TEXT NOT NULL DEFAULT '',
    detail   TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_steps_run ON steps(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_steps_session ON steps(session, seq);
CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    session       TEXT NOT NULL DEFAULT '',
    subagent      TEXT NOT NULL DEFAULT '',
    started_ts    REAL NOT NULL DEFAULT 0,
    ended_ts      REAL NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'running',
    steps         INTEGER NOT NULL DEFAULT 0,
    tool_calls    INTEGER NOT NULL DEFAULT 0,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    last_seq      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

#: Event types the projection folds; everything else is skipped by the read filter.
_SOURCE_TYPES = (
    DomainEvent.AGENT_STEP,
    RuntimeEvent.RUN_STARTED,
    RuntimeEvent.AGENT_COMPLETED,
    RuntimeEvent.RUN_FAILED,
    RuntimeEvent.RUN_CANCELLED,
    RuntimeEvent.AGENT_CANCELLED,
)
_TERMINAL = {
    RuntimeEvent.AGENT_COMPLETED: "completed",
    RuntimeEvent.RUN_FAILED: "failed",
    RuntimeEvent.RUN_CANCELLED: "cancelled",
    RuntimeEvent.AGENT_CANCELLED: "cancelled",
}
_PAGE = 500


class TrajectoryStore:
    def __init__(self, db_path: str | Path, log: EventLog) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()
        self._closed = False
        self._log = log

    # -- projection (single writer) ------------------------------------------

    def projected_seq(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key = 'projected_seq'"
            ).fetchone()
        return int(row[0]) if row else 0

    def catch_up(self) -> int:
        """Fold every unprojected source event; returns the number folded.
        Safe to call concurrently (serialized by the lock) and repeatedly."""
        folded = 0
        while True:
            if self._closed:
                return folded
            # Log reads happen WITHOUT the projection lock: the event bus may
            # hold its own lock while dispatching to this store, so taking the
            # projection lock first would invert the lock order and deadlock.
            # Re-reads are safe: folding is idempotent (INSERT OR IGNORE) and
            # the cursor only moves forward.
            start = self.projected_seq()
            rows = self._log.read_after(after_seq=start, types=_SOURCE_TYPES, limit=_PAGE)
            if not rows:
                return folded
            with self._lock:
                if self._closed:
                    return folded
                for seq, event in rows:
                    if seq <= start:
                        continue  # folded by a concurrent catch_up in between
                    self._fold(seq, event)
                    folded += 1
                self._conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES ('projected_seq', ?)",
                    (str(rows[-1][0]),),
                )
                self._conn.commit()
            if len(rows) < _PAGE:
                return folded

    def _fold(self, seq: int, event: Event) -> None:
        payload = event.payload or {}
        run_id = str(payload.get("run_id") or "")
        if event.type == DomainEvent.AGENT_STEP:
            detail = payload.get("detail") or {}
            inserted = self._conn.execute(
                "INSERT OR IGNORE INTO steps (seq, run_id, session, subagent, ts, trace_id, actor,"
                " kind, name, summary, detail) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    seq,
                    run_id,
                    str(payload.get("session") or ""),
                    str(payload.get("subagent") or ""),
                    event.ts,
                    event.trace_id,
                    json.dumps(event.actor.to_dict(), ensure_ascii=False),
                    str(payload.get("kind") or ""),
                    str(payload.get("name") or ""),
                    str(payload.get("summary") or ""),
                    json.dumps(detail, ensure_ascii=False, default=str),
                ),
            )
            if inserted.rowcount and run_id:
                kind = str(payload.get("kind") or "")
                self._conn.execute(
                    "INSERT INTO runs (run_id, session, subagent, started_ts, last_seq)"
                    " VALUES (?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET"
                    " session = CASE WHEN runs.session = '' THEN excluded.session ELSE runs.session END,"
                    " subagent = CASE WHEN runs.subagent = '' THEN excluded.subagent ELSE runs.subagent END,"
                    " last_seq = MAX(runs.last_seq, excluded.last_seq)",
                    (
                        run_id,
                        str(payload.get("session") or ""),
                        str(payload.get("subagent") or ""),
                        event.ts,
                        seq,
                    ),
                )
                self._conn.execute(
                    "UPDATE runs SET steps = steps + 1, tool_calls = tool_calls + ?,"
                    " input_tokens = input_tokens + ?, output_tokens = output_tokens + ?"
                    " WHERE run_id = ?",
                    (
                        1 if kind == "tool" else 0,
                        int(detail.get("input_tokens") or 0) if isinstance(detail, dict) else 0,
                        int(detail.get("output_tokens") or 0) if isinstance(detail, dict) else 0,
                        run_id,
                    ),
                )
            return
        if not run_id:
            return
        if event.type == RuntimeEvent.RUN_STARTED:
            self._conn.execute(
                "INSERT INTO runs (run_id, subagent, started_ts, status, last_seq)"
                " VALUES (?,?,?,'running',?) ON CONFLICT(run_id) DO UPDATE SET"
                " started_ts = CASE WHEN runs.started_ts = 0 THEN excluded.started_ts ELSE runs.started_ts END,"
                " status = 'running', last_seq = MAX(runs.last_seq, excluded.last_seq)",
                (run_id, str(payload.get("subagent") or ""), event.ts, seq),
            )
            return
        status = _TERMINAL.get(event.type)
        if status is not None:
            self._conn.execute(
                "INSERT INTO runs (run_id, started_ts, ended_ts, status, last_seq)"
                " VALUES (?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET"
                " ended_ts = excluded.ended_ts, status = excluded.status,"
                " last_seq = MAX(runs.last_seq, excluded.last_seq)",
                (run_id, event.ts, event.ts, status, seq),
            )

    # -- reads (never touch the log) ------------------------------------------

    def steps_page(
        self,
        *,
        session: str = "",
        after_seq: int = 0,
        before_seq: int | None = None,
        limit: int = 200,
    ) -> tuple[list[dict[str, Any]], bool]:
        """One page of step rows in event-dict shape under the chat cursor
        contract (newest window by default; after_seq forward; before_seq
        backward); returns (rows, has_more)."""
        cap = max(1, limit)
        where = ["session = ?"] if session else []
        params: list[Any] = [session] if session else []
        if after_seq > 0:
            where.append("seq > ?")
            params.append(after_seq)
            order, trim_head = "ASC", False
        else:
            if before_seq is not None:
                where.append("seq < ?")
                params.append(before_seq)
            order, trim_head = "DESC", True
        sql = "SELECT seq, run_id, session, subagent, ts, trace_id, actor, kind, name, summary, detail FROM steps"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY seq {order} LIMIT ?"
        params.append(cap + 1)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        has_more = len(rows) > cap
        rows = rows[:cap]
        if trim_head:
            rows.reverse()
        return [_step_row(r) for r in rows], has_more

    def run_steps(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, run_id, session, subagent, ts, trace_id, actor, kind, name, summary, detail"
                " FROM steps WHERE run_id = ? ORDER BY seq ASC",
                (run_id,),
            ).fetchall()
        return [_step_row(r) for r in rows]

    def list_runs(self, *, session: str = "", limit: int = 50) -> list[dict[str, Any]]:
        sql = (
            "SELECT run_id, session, subagent, started_ts, ended_ts, status, steps, tool_calls,"
            " input_tokens, output_tokens, last_seq FROM runs"
        )
        params: list[Any] = []
        if session:
            sql += " WHERE session = ?"
            params.append(session)
        sql += " ORDER BY last_seq DESC LIMIT ?"
        params.append(max(1, limit))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        keys = (
            "run_id",
            "session",
            "subagent",
            "started_ts",
            "ended_ts",
            "status",
            "steps",
            "tool_calls",
            "input_tokens",
            "output_tokens",
            "last_seq",
        )
        return [dict(zip(keys, r)) for r in rows]

    def close(self) -> None:
        """Stop folding first, then close: an in-flight catch_up finishes its
        fold section (same lock) before the connection goes away; a later
        catch_up sees _closed and returns without touching the log again."""
        with self._lock:
            self._closed = True
            self._conn.close()


def _step_row(r: tuple) -> dict[str, Any]:
    """Event-dict shape (id omitted: the log seq is the identity here)."""
    return {
        "seq": r[0],
        "type": DomainEvent.AGENT_STEP,
        "actor": json.loads(r[6]),
        "payload": {
            "run_id": r[1],
            "session": r[2],
            "subagent": r[3],
            "kind": r[7],
            "name": r[8],
            "summary": r[9],
            "detail": json.loads(r[10]),
        },
        "ts": r[4],
        "trace_id": r[5],
    }


__all__ = ["TrajectoryStore"]
