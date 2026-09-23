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
import time
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
CREATE TABLE IF NOT EXISTS raw_rounds (
    run_id   TEXT NOT NULL,
    round    INTEGER NOT NULL,
    session  TEXT NOT NULL DEFAULT '',
    ts       REAL NOT NULL,
    request  TEXT NOT NULL DEFAULT '',
    response TEXT NOT NULL DEFAULT '',
    seq_round INTEGER NOT NULL DEFAULT 0,
    wire_request TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (run_id, round)
);
CREATE INDEX IF NOT EXISTS idx_raw_rounds_session ON raw_rounds(session, seq_round);
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
        # Migration for databases created before seq_round/wire_request existed:
        # CREATE TABLE IF NOT EXISTS cannot add columns to an existing table.
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(raw_rounds)").fetchall()}
        if "seq_round" not in cols:
            self._conn.execute(
                "ALTER TABLE raw_rounds ADD COLUMN seq_round INTEGER NOT NULL DEFAULT 0"
            )
        if "wire_request" not in cols:
            self._conn.execute(
                "ALTER TABLE raw_rounds ADD COLUMN wire_request TEXT NOT NULL DEFAULT ''"
            )
        # executescript above already created the index on fresh databases;
        # for pre-existing ones the CREATE INDEX IF NOT EXISTS in _SCHEMA ran
        # before the ALTER, so re-run it now that all columns exist.
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_raw_rounds_session ON raw_rounds(session, seq_round)"
        )
        # Backfill session-global numbering for rows written before the
        # column existed (seq_round = 0): renumber each session's rows by
        # timestamp so the log page shows one continuous sequence across
        # process restarts instead of one sequence per run_id. Rows already
        # numbered (post-migration writes) keep theirs; new numbers continue
        # after the session's max. Done in Python with an explicit ORDER BY:
        # a single UPDATE with correlated subqueries would see its own partial
        # writes (live-state semantics), making the numbering depend on the
        # row scan order instead of the ts order promised here. The per-row
        # MAX is hoisted into one GROUP BY up front and the updates go out as
        # one executemany: this runs on the startup path, and on a large
        # legacy DB (six-figure rows) 2n statements measure in minutes while
        # n+1 measure in seconds.
        with self._conn:
            pending = self._conn.execute(
                "SELECT session, run_id, round FROM raw_rounds WHERE seq_round = 0"
                " ORDER BY session, ts, round, run_id"
            ).fetchall()
            if pending:
                maxes = dict(
                    self._conn.execute(
                        "SELECT session, MAX(seq_round) FROM raw_rounds GROUP BY session"
                    ).fetchall()
                )
                updates: list[tuple[int, str, int]] = []
                current: str | None = None
                base = 0
                for session, run_id, round_no in pending:
                    if session != current:
                        current = session
                        base = int(maxes.get(session, 0))
                    base += 1
                    updates.append((base, run_id, round_no))
                self._conn.executemany(
                    "UPDATE raw_rounds SET seq_round = ? WHERE run_id = ? AND round = ?", updates
                )
        self._conn.commit()
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

    # -- raw LLM round log ----------------------------------------------------
    #
    # The steps projection is a display surface; the raw table keeps one full
    # request transcript + response per round (verbatim, nothing truncated)
    # so the UI can show exactly what the model saw and answered.

    def record_raw_round(
        self,
        *,
        run_id: str,
        session: str,
        round: int,
        request: str,
        response: str,
        wire_request: str = "",
    ) -> None:
        # Round numbering is session-global: run-scoped rounds restart at 1 on
        # every process restart / new run_id, so the log page would show two
        # colliding number sequences in one session. MAX(round)+1 per session
        # keeps the displayed number monotonic with time; `round` (the
        # run-scoped counter) is kept as a tiebreaker for same-tick inserts.
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(seq_round), 0) + 1 FROM raw_rounds WHERE session = ?",
                (session,),
            ).fetchone()
            seq_round = int(row[0])
            self._conn.execute(
                "INSERT OR REPLACE INTO raw_rounds"
                " (run_id, round, session, ts, request, response, seq_round, wire_request)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    int(round),
                    session,
                    time.time(),
                    request,
                    response,
                    seq_round,
                    wire_request,
                ),
            )
            self._conn.commit()

    def raw_rounds(self, run_id: str) -> list[dict[str, Any]]:
        """Round index for one run: round numbers, timestamps and body sizes —
        no bodies, so listing stays cheap."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT round, ts, length(request), length(response)"
                " FROM raw_rounds WHERE run_id = ? ORDER BY round ASC",
                (run_id,),
            ).fetchall()
        return [
            {"round": r[0], "ts": r[1], "request_bytes": r[2], "response_bytes": r[3]} for r in rows
        ]

    def raw_rounds_for_session(
        self, session: str, *, limit: int = 200
    ) -> tuple[list[dict[str, Any]], int]:
        """Full raw bodies of the newest `limit` rounds of one session,
        oldest first (the chat log page renders this verbatim), plus the
        total recorded count so the UI can say how much older exists."""
        capped = max(1, limit)
        with self._lock:
            total = int(
                self._conn.execute(
                    "SELECT COUNT(*) FROM raw_rounds WHERE session = ?", (session,)
                ).fetchone()[0]
            )
            rows = self._conn.execute(
                "SELECT run_id, round, session, ts, request, response, seq_round, wire_request"
                # seq_round (session-global, monotonic) leads; ts is the
                # tiebreaker for rows written before the migration
                " FROM raw_rounds WHERE session = ? ORDER BY seq_round DESC, ts DESC LIMIT ?",
                (session, capped),
            ).fetchall()
        rounds = [
            {
                "run_id": r[0],
                "round": r[6] or r[1],  # legacy rows: fall back to the run-scoped round
                "session": r[2],
                "ts": r[3],
                "request": r[4],
                "response": r[5],
                "wire_request": r[7],
            }
            for r in reversed(rows)  # DESC select -> return oldest first
        ]
        return rounds, total

    def purge_raw_older_than_days(self, days: int) -> int:
        """Startup retention for the raw LLM log: it is a debugging surface,
        not an archive — bodies are the full per-round transcripts and would
        otherwise grow without bound. Returns the deleted row count."""
        if days <= 0:
            return 0
        cutoff = time.time() - days * 86400.0
        with self._lock:
            cur = self._conn.execute("DELETE FROM raw_rounds WHERE ts < ?", (cutoff,))
            self._conn.commit()
        return int(cur.rowcount or 0)

    def raw_round(self, run_id: str, round: int) -> dict[str, Any] | None:
        """Full raw bodies of one round; None when not recorded. `round` is
        the run-scoped key; the returned `round` is the display number
        (session-global when known, the run-scoped one for legacy rows)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT run_id, round, session, ts, request, response, seq_round, wire_request"
                " FROM raw_rounds WHERE run_id = ? AND round = ?",
                (run_id, int(round)),
            ).fetchone()
        if row is None:
            return None
        return {
            "run_id": row[0],
            "round": row[6] or row[1],
            "session": row[2],
            "ts": row[3],
            "request": row[4],
            "response": row[5],
            "wire_request": row[7],
        }


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
