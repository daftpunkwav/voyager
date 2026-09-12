"""code-exec data access: execution history and artifact metadata.

Execution results themselves are returned via the event stream; artifact
files land under workspace/sandbox/artifacts/<job_id>/.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS executions (
    id         TEXT PRIMARY KEY,
    runtime    TEXT NOT NULL,
    kind       TEXT NOT NULL,
    status     TEXT NOT NULL,
    exit_code  INTEGER,
    stdout     TEXT NOT NULL DEFAULT '',
    stderr     TEXT NOT NULL DEFAULT '',
    artifact_dir TEXT,
    created_ts REAL NOT NULL,
    updated_ts REAL NOT NULL
);
"""

_COLS = (
    "id",
    "runtime",
    "kind",
    "status",
    "exit_code",
    "stdout",
    "stderr",
    "artifact_dir",
    "created_ts",
    "updated_ts",
)


class ExecutionStore:
    """Execution records: separate namespace, tables not shared with other
    packages."""

    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def create(self, exec_id: str, runtime: str, kind: str) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO executions (id, runtime, kind, status, created_ts, updated_ts)"
                " VALUES (?, ?, ?, 'running', ?, ?)",
                (exec_id, runtime, kind, now, now),
            )
            self._conn.commit()

    def finish(
        self,
        exec_id: str,
        status: str,
        exit_code: int | None,
        stdout: str,
        stderr: str,
        artifact_dir: str = "",
    ) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE executions SET status=?, exit_code=?, stdout=?, stderr=?,"
                " artifact_dir=?, updated_ts=? WHERE id=?",
                (status, exit_code, stdout, stderr, artifact_dir, time.time(), exec_id),
            )
            self._conn.commit()

    def get(self, exec_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                f"SELECT {','.join(_COLS)} FROM executions WHERE id=?", (exec_id,)
            ).fetchone()
        return _row(_COLS, row) if row else None

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {','.join(_COLS)} FROM executions ORDER BY created_ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row(_COLS, r) for r in rows]

    def close(self) -> None:
        self._conn.close()


def _row(cols: tuple[str, ...], r: tuple) -> dict[str, Any]:
    return dict(zip(cols, r))
