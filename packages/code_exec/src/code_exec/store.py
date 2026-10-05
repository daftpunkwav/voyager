"""code-exec data access: execution history and artifact metadata.

Execution results themselves are returned via the event stream; artifact
files land under workspace/sandbox/artifacts/<job_id>/.

Retention: rows carry up to ~1MB per output column and artifact dirs
accumulate whatever executed code wrote; without a policy both grow without
bound. Pruning is age-based with a row-count cap (burst loops), and removes
the artifact directories of purged rows plus long-abandoned orphan dirs
(crash between dir creation and row insert).
"""

from __future__ import annotations

import shutil
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

# Plain-literal SELECT heads; the column lists are kept in lockstep with
# _COLS (which feeds _row via zip), never widened to *.
_SQL_GET_EXEC = (
    "SELECT id, runtime, kind, status, exit_code, stdout, stderr, artifact_dir,"
    " created_ts, updated_ts FROM executions WHERE id=?"
)
_SQL_LIST_RECENT = (
    "SELECT id, runtime, kind, status, exit_code, stdout, stderr, artifact_dir,"
    " created_ts, updated_ts FROM executions"
    " ORDER BY created_ts DESC, rowid DESC LIMIT ?"
)

#: Keep finished executions for 30 days, at most 200 rows (each row may hold
#: up to ~1MB stdout + ~1MB stderr, so the cap bounds burst loops at a few
#: hundred MB worst case).
_MAX_AGE_S = 30 * 86400.0
_MAX_ROWS = 200
#: Prune at most once per this many creates: the sweep is cheap but not free,
#: and every create does not need one.
_PRUNE_EVERY = 32


class ExecutionStore:
    """Execution records: separate namespace, tables not shared with other
    packages."""

    def __init__(self, db_path: str | Path, *, artifact_root: str | Path | None = None) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()
        self._artifact_root = Path(artifact_root) if artifact_root is not None else None
        self._ops = 0
        self.prune()

    def create(self, exec_id: str, runtime: str, kind: str) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO executions (id, runtime, kind, status, created_ts, updated_ts)"
                " VALUES (?, ?, ?, 'running', ?, ?)",
                (exec_id, runtime, kind, now, now),
            )
            self._conn.commit()
        self._ops += 1
        if self._ops % _PRUNE_EVERY == 0:
            self.prune()

    def prune(self, *, now: float | None = None) -> int:
        """Apply the retention policy once; returns purged row count.

        Deletes rows older than the retention age and rows beyond the count
        cap (newest kept), removing each purged row's artifact directory plus
        orphan artifact dirs whose mtime is older than the retention age (a
        crash between dir creation and row insert). Best-effort on the
        filesystem side: a dir that cannot be removed never blocks the DB
        cleanup, and a fresh dir (a run in flight) is never touched — its
        mtime is recent by definition.
        """
        current = time.time() if now is None else now
        cutoff = current - _MAX_AGE_S
        with self._lock:
            old = self._conn.execute(
                "SELECT id FROM executions WHERE updated_ts < ?", (cutoff,)
            ).fetchall()
            extra = self._conn.execute(
                "SELECT id FROM executions ORDER BY updated_ts DESC, rowid DESC LIMIT -1 OFFSET ?",
                (_MAX_ROWS,),
            ).fetchall()
            ids = [r[0] for r in old] + [r[0] for r in extra]
            if ids:
                marks = ",".join("?" for _ in ids)
                # Bound parameters only; the IN-list length drives the mark count.
                self._conn.execute(
                    f"DELETE FROM executions WHERE id IN ({marks})",  # nosec B608  # nosemgrep
                    ids,
                )
                self._conn.commit()
        for exec_id in ids:
            self._remove_artifacts(exec_id)
        self._sweep_orphan_artifacts(cutoff)
        return len(ids)

    def _remove_artifacts(self, exec_id: str) -> None:
        """Remove one purged execution's artifact directory (best-effort).

        ids are server-generated hex at insert time, so the join below stays
        inside the artifact root by construction.
        """
        if self._artifact_root is None:
            return
        shutil.rmtree(self._artifact_root / exec_id, ignore_errors=True)

    def _sweep_orphan_artifacts(self, cutoff: float) -> None:
        """Remove artifact dirs with no live row and an mtime older than the
        cutoff (crash leftovers; a fresh mtime means the run may be in
        flight, so it stays)."""
        root = self._artifact_root
        if root is None or not root.is_dir():
            return
        try:
            children = list(root.iterdir())
        except OSError:
            return
        with self._lock:
            live = {r[0] for r in self._conn.execute("SELECT id FROM executions").fetchall()}
        for child in children:
            if child.name in live:
                continue
            try:
                if child.stat().st_mtime < cutoff:
                    shutil.rmtree(child, ignore_errors=True)
            except OSError:
                continue

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
            row = self._conn.execute(_SQL_GET_EXEC, (exec_id,)).fetchone()
        return _row(_COLS, row) if row else None

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            # rowid DESC breaks created_ts ties (a burst of creates inside one
            # clock tick): "newest" must match prune's row selection, which
            # already tiebreaks by rowid, or the history order is arbitrary.
            rows = self._conn.execute(_SQL_LIST_RECENT, (limit,)).fetchall()
        return [_row(_COLS, r) for r in rows]

    def close(self) -> None:
        self._conn.close()


def _row(cols: tuple[str, ...], r: tuple) -> dict[str, Any]:
    return dict(zip(cols, r))
