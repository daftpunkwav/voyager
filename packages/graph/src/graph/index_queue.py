"""Persistent priority queue for graph index jobs (enqueue / cancel
/ reorder).

Responsibilities:
- Enqueue / cancel / reorder index jobs with priorities
- Persist jobs in SQLite across restarts
- Track the queued->running->done/failed/cancelled state machine
- Carry the L0/L1 job levels (deep single-resource analysis vs cross-resource
  relation analysis)

Jobs are stored in SQLite so they survive restarts. Cancellation needs no
generation-invalidation scheme: the queued->running->done/failed/cancelled
state machine plus a scheduler-side status re-check before execution suffice.

Job levels follow the L0/L1 layering: level="l1" is deep analysis of a single
resource (code repository, via repo_path); level="l0" is cross-resource
relation analysis (resource kinds subset via kinds, repo_path empty).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS index_jobs (
    id         TEXT PRIMARY KEY,
    project    TEXT NOT NULL,
    repo_path  TEXT NOT NULL,
    priority   INTEGER NOT NULL DEFAULT 100,
    status     TEXT NOT NULL DEFAULT 'queued',
    attempts   INTEGER NOT NULL DEFAULT 0,
    error      TEXT NOT NULL DEFAULT '',
    created_ts REAL NOT NULL,
    updated_ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON index_jobs(status, priority, created_ts);
"""

#: Incremental columns for pre-existing databases (level/kinds); not in the
#: CREATE TABLE statement, always added by _migrate.
_MIGRATE_COLS = {"level": "TEXT NOT NULL DEFAULT 'l1'", "kinds": "TEXT NOT NULL DEFAULT '[]'"}

_COLS = (
    "id",
    "project",
    "repo_path",
    "priority",
    "status",
    "attempts",
    "error",
    "created_ts",
    "updated_ts",
    "level",
    "kinds",
)


class IndexQueue:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._lock = threading.Lock()

    def _migrate(self) -> None:
        """Idempotently add missing columns to older databases via ALTER TABLE."""
        have = {r[1] for r in self._conn.execute("PRAGMA table_info(index_jobs)")}
        for col, ddl in _MIGRATE_COLS.items():
            if col not in have:
                self._conn.execute(f"ALTER TABLE index_jobs ADD COLUMN {col} {ddl}")
        self._conn.commit()

    def enqueue(
        self,
        project: str,
        repo_path: str,
        priority: int = 100,
        *,
        level: str = "l1",
        kinds: list[str] | None = None,
    ) -> str:
        jid = uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO index_jobs (id, project, repo_path, priority, status,"
                " created_ts, updated_ts, level, kinds)"
                " VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?)",
                (
                    jid,
                    project,
                    repo_path,
                    priority,
                    now,
                    now,
                    level,
                    json.dumps(kinds or [], ensure_ascii=False),
                ),
            )
            self._conn.commit()
        return jid

    def cancel(self, jid: str) -> bool:
        """Only queued jobs can be cancelled; running jobs are stopped cooperatively."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE index_jobs SET status='cancelled', updated_ts=?"
                " WHERE id=? AND status='queued'",
                (time.time(), jid),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def reorder(self, jid: str, priority: int) -> bool:
        """Adjust priority (lower value runs first)."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE index_jobs SET priority=?, updated_ts=? WHERE id=? AND status='queued'",
                (priority, time.time(), jid),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def next(self) -> dict[str, Any] | None:
        """Dequeue the highest-priority queued job and mark it running (single scheduler)."""
        with self._lock:
            row = self._conn.execute(
                f"SELECT {','.join(_COLS)} FROM index_jobs WHERE status='queued'"
                " ORDER BY priority ASC, created_ts ASC LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            self._conn.execute(
                "UPDATE index_jobs SET status='running', attempts=attempts+1,"
                " updated_ts=? WHERE id=?",
                (time.time(), row[0]),
            )
            self._conn.commit()
        job = _row(row)
        job["status"] = "running"
        job["attempts"] += 1  # report the incremented value; retry decisions rely on it
        return job

    def finish(self, jid: str, *, ok: bool, error: str = "", retry: bool = False) -> None:
        status = "queued" if retry else ("done" if ok else "failed")
        with self._lock:
            self._conn.execute(
                "UPDATE index_jobs SET status=?, error=?, updated_ts=? WHERE id=?",
                (status, error[:500], time.time(), jid),
            )
            self._conn.commit()

    def get(self, jid: str) -> dict[str, Any] | None:
        # Reads and writes share the same lock (reads used to race with the
        # scheduler thread's status transitions).
        with self._lock:
            row = self._conn.execute(
                f"SELECT {','.join(_COLS)} FROM index_jobs WHERE id=?", (jid,)
            ).fetchone()
        return _row(row) if row else None

    def list(self, status: str = "") -> list[dict[str, Any]]:
        sql = f"SELECT {','.join(_COLS)} FROM index_jobs"
        params: tuple = ()
        if status:
            sql += " WHERE status=?"
            params = (status,)
        with self._lock:
            rows = self._conn.execute(
                f"{sql} ORDER BY priority ASC, created_ts ASC", params
            ).fetchall()
        return [_row(r) for r in rows]

    def close(self) -> None:
        self._conn.close()


def _row(r: tuple) -> dict[str, Any]:
    d = dict(zip(_COLS, r))
    try:
        d["kinds"] = json.loads(d.get("kinds") or "[]")
    except (TypeError, ValueError):
        d["kinds"] = []
    return d
