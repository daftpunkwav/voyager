"""Persistent event log: an append-only SQLite table.

seq is auto-incrementing and defines the total order of events.
"""

from __future__ import annotations

import fnmatch
import json
import sqlite3
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from platform_contracts import Event

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq      INTEGER PRIMARY KEY AUTOINCREMENT,
    id       TEXT NOT NULL UNIQUE,
    type     TEXT NOT NULL,
    actor    TEXT NOT NULL,
    payload  TEXT NOT NULL,
    ts       REAL NOT NULL,
    trace_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
CREATE INDEX IF NOT EXISTS idx_events_ts   ON events(ts);
"""

#: fnmatch wildcards (same semantics as Subscription.matches: fnmatchcase)
_GLOB_CHARS = frozenset("*?[")

#: Raw rows fetched per window when glob refinement is active: generous
#: enough that sparse matches (few refined hits per raw page) need few round
#: trips, while each query stays an index range scan.
_GLOB_WINDOW = 1000


@dataclass(frozen=True)
class Retention:
    """Deletion policy for high-churn event types.

    Streaming delta events (one row per text chunk) are an ephemeral display
    stream; without a policy the log grows monotonically and replay slows
    down. Callers name the types and the max age; the platform stays generic
    and never hardcodes business event names. Sweeps run at construction
    time and every ``sweep_every`` appends.

    Cursors below the deleted range simply resume from the first surviving
    seq. Deleted pages are reused by SQLite, so growth stops even though the
    file does not shrink (run VACUUM manually if the file must shrink).
    """

    types: tuple[str, ...]
    max_age_s: float
    #: Appends between sweeps (sweeps are cheap but not free)
    sweep_every: int = 500


def _like_prefix(pattern: str) -> str:
    """Literal prefix of a glob pattern (for LIKE narrowing): truncate at the
    first wildcard and escape LIKE metacharacters."""
    prefix = pattern
    for ch in _GLOB_CHARS:
        prefix = prefix.split(ch, 1)[0]
    return prefix.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def _type_condition(types: Iterable[str], params: list[object]) -> str | None:
    """SQL WHERE fragment matching event types with subscription semantics:
    exact types go through SQL IN; glob patterns narrow candidates with a
    prefix LIKE (avoiding a full scan on very large logs). Shared by
    read_after / read_before; bound parameters are appended to params."""
    exact: list[str] = []
    globs: list[str] = []
    for t in types:
        (globs if _GLOB_CHARS & set(t) else exact).append(t)
    conds: list[str] = []
    if exact:
        placeholders = ",".join("?" for _ in exact)
        conds.append(f"type IN ({placeholders})")
        params.extend(exact)
    if globs:
        likes = []
        for g in globs:
            likes.append("type LIKE ? ESCAPE '\\'")
            params.append(_like_prefix(g) + "%")
        conds.append("(" + " OR ".join(likes) + ")")
    if not conds:
        return None
    return "(" + " OR ".join(conds) + ")"


def _refine_rows(rows: list[tuple], exact: list[str], globs: list[str]) -> list[tuple]:
    """Post-LIKE refinement: glob candidates are kept only when fnmatch
    accepts them (a literal 'task.*' would over-match via prefix LIKE);
    exact IN hits must be kept as-is."""
    if not globs:
        return rows
    exact_set = set(exact)
    return [
        r for r in rows if r[2] in exact_set or any(fnmatch.fnmatchcase(r[2], g) for g in globs)
    ]


class EventLog:
    """Append-only writes, ordered reads.

    Thread-safe (single connection with one shared read/write lock); the same
    db file may be shared across processes.
    """

    def __init__(self, db_path: str | Path, *, retention: Retention | None = None) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()
        self._retention = retention
        self._appends = 0
        if retention is not None:
            self._sweep()

    @property
    def conn(self) -> sqlite3.Connection:
        """Shared connection for CursorStore and friends (in-framework
        convention; external reads should use the public query methods)."""
        return self._conn

    @property
    def lock(self) -> threading.Lock:
        """Callers sharing the connection (CursorStore etc.) must share this
        lock for all reads and writes."""
        return self._lock

    def purge(self, types: Iterable[str], *, before_ts: float) -> int:
        """Delete events of the given exact types older than before_ts.

        Returns the number of deleted rows. Bounds growth of high-churn
        event types; the public entry point so callers can sweep manually
        (the retention policy does this automatically).
        """
        type_list = list(types)
        if not type_list:
            return 0
        placeholders = ",".join("?" for _ in type_list)
        with self._lock:
            cur = self._conn.execute(
                f"DELETE FROM events WHERE type IN ({placeholders}) AND ts < ?",
                (*type_list, before_ts),
            )
            self._conn.commit()
        return max(int(cur.rowcount or 0), 0)  # drivers may report -1 for unknown

    def _sweep(self) -> None:
        """Apply the retention policy once (no-op without one)."""
        if self._retention is None:
            return
        cutoff = time.time() - self._retention.max_age_s
        self.purge(self._retention.types, before_ts=cutoff)

    def latest_seq(self) -> int:
        """Current maximum seq (0 for an empty table). Public read access for
        SSE resume and similar, instead of touching conn directly."""
        with self._lock:
            row = self._conn.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()
        return int(row[0])

    def append(self, event: Event) -> int:
        """Append an event; returns its total-order seq."""
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO events (id, type, actor, payload, ts, trace_id)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event.id,
                    event.type,
                    json.dumps(event.actor.to_dict(), ensure_ascii=False),
                    json.dumps(event.payload, ensure_ascii=False),
                    event.ts,
                    event.trace_id,
                ),
            )
            self._conn.commit()
            self._appends += 1  # under the lock: publish fans appends out to threads
            sweep_due = (
                self._retention is not None
                and self._retention.sweep_every > 0
                and self._appends % self._retention.sweep_every == 0
            )
        if cur.lastrowid is None:  # unreachable: an INSERT always yields a rowid
            raise RuntimeError("event append produced no rowid")
        if sweep_due:
            # Outside the append lock: purge re-acquires it (not reentrant).
            self._sweep()
        return int(cur.lastrowid)

    def read_after(
        self,
        after_seq: int = 0,
        types: Iterable[str] | None = None,
        limit: int = 500,
    ) -> list[tuple[int, Event]]:
        """Read events with seq > after_seq (optionally filtered by type),
        ordered by seq ascending.

        Type filters follow subscription semantics: exact types go through
        SQL IN; glob-pattern entries first narrow candidates with a prefix
        LIKE (avoiding a full scan on very large logs), then refine with
        fnmatch. The refinement matters because a literal 'task.*' would not
        be matched by IN, so catch-up stays consistent with push delivery.

        Glob refinement runs BEFORE the limit is applied: a page that loses
        rows to refinement must not masquerade as the tail (callers treat a
        short page as "no more rows"), so refined matches are collected in
        raw windows until `limit` matches or the log ends.
        """
        sql = "SELECT seq, id, type, actor, payload, ts, trace_id FROM events WHERE seq > ?"
        params: list[object] = [after_seq]
        exact: list[str] = []
        globs: list[str] = []
        if types:
            cond = _type_condition(types, params)
            if cond:
                sql += " AND " + cond
                exact = [t for t in types if not (_GLOB_CHARS & set(t))]
                globs = [t for t in types if _GLOB_CHARS & set(t)]
        if not globs:
            sql += " ORDER BY seq ASC LIMIT ?"
            params.append(limit)
            with self._lock:
                rows = self._conn.execute(sql, params).fetchall()
            return [(int(r[0]), _row_to_event(r)) for r in rows]
        collected: list[tuple] = []
        cursor = after_seq
        while len(collected) < limit:
            window_sql = sql + " ORDER BY seq ASC LIMIT ?"
            window_params = [*params, max(limit, _GLOB_WINDOW)]
            with self._lock:
                rows = self._conn.execute(window_sql, window_params).fetchall()
            if not rows:
                break
            cursor = int(rows[-1][0])
            collected.extend(_refine_rows(rows, exact, globs))
            # Narrow the next window past everything just read (matches and
            # refined-out rows alike), so sparse matches cannot loop forever
            sql = "SELECT seq, id, type, actor, payload, ts, trace_id FROM events WHERE seq > ?"
            params = [cursor]
            if types:
                cond = _type_condition(types, params)
                if cond:
                    sql += " AND " + cond
        return [(int(r[0]), _row_to_event(r)) for r in collected[:limit]]

    def read_before(
        self,
        before_seq: int,
        types: Iterable[str] | None = None,
        limit: int = 500,
    ) -> list[tuple[int, Event]]:
        """Read the `limit` events with seq < before_seq closest to it
        (optionally filtered by type), returned ascending.

        Window selection walks backwards (ORDER BY seq DESC) so the result is
        the page immediately before the cursor, not the oldest page — this is
        what makes backward history paging behave as "load earlier events".
        Type filters use the same subscription semantics as read_after.
        Glob refinement runs BEFORE the limit is applied (same contract as
        read_after: a refined-short page must not masquerade as the head of
        the remaining log).
        """
        sql = "SELECT seq, id, type, actor, payload, ts, trace_id FROM events WHERE seq < ?"
        params: list[object] = [before_seq]
        exact: list[str] = []
        globs: list[str] = []
        if types:
            cond = _type_condition(types, params)
            if cond:
                sql += " AND " + cond
                exact = [t for t in types if not (_GLOB_CHARS & set(t))]
                globs = [t for t in types if _GLOB_CHARS & set(t)]
        if not globs:
            sql += " ORDER BY seq DESC LIMIT ?"
            params.append(limit)
            with self._lock:
                rows = self._conn.execute(sql, params).fetchall()
            rows.reverse()
            return [(int(r[0]), _row_to_event(r)) for r in rows]
        collected: list[tuple] = []
        cursor = before_seq
        while len(collected) < limit:
            window_sql = sql + " ORDER BY seq DESC LIMIT ?"
            window_params = [*params, max(limit, _GLOB_WINDOW)]
            with self._lock:
                rows = self._conn.execute(window_sql, window_params).fetchall()
            if not rows:
                break
            cursor = int(rows[-1][0])
            collected[:0] = _refine_rows(rows, exact, globs)
            # Narrow the next window below everything just read (matches and
            # refined-out rows alike), so sparse matches cannot loop forever
            sql = "SELECT seq, id, type, actor, payload, ts, trace_id FROM events WHERE seq < ?"
            params = [cursor]
            if types:
                cond = _type_condition(types, params)
                if cond:
                    sql += " AND " + cond
        # collected is newest-first (DESC windows prepended): the page closest
        # to before_seq is its head; return it in ascending order
        kept = collected[:limit]
        kept.reverse()
        return [(int(r[0]), _row_to_event(r)) for r in kept]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _row_to_event(row: tuple) -> Event:
    from platform_contracts import ActorRef

    return Event(
        id=row[1],
        type=row[2],
        actor=ActorRef.from_dict(json.loads(row[3])),
        payload=json.loads(row[4]),
        ts=float(row[5]),
        trace_id=row[6],
    )
