"""Data access for the browser service: session metadata only, no
business data.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    url        TEXT,
    created_ts REAL NOT NULL,
    updated_ts REAL NOT NULL
);
"""

_COLS = ("id", "url", "created_ts", "updated_ts")

# Plain-literal SELECT heads: the column list is kept in lockstep with _COLS
# (which feeds _row via zip), never widened to *.
_SQL_GET_SESSION = "SELECT id, url, created_ts, updated_ts FROM sessions WHERE id=?"


class BrowserStore:
    """Session metadata only; kept for debugging and auditing, not business data."""

    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def touch(self, sid: str, url: str = "") -> dict[str, Any]:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions (id, url, created_ts, updated_ts)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET url=excluded.url,"
                " updated_ts=excluded.updated_ts",
                (sid, url, now, now),
            )
            self._conn.commit()
        created = self.get(sid)
        if created is None:  # unreachable: the row was written above
            raise KeyError(sid)
        return created

    def get(self, sid: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(_SQL_GET_SESSION, (sid,)).fetchone()
        return _row(_COLS, row) if row else None

    def close(self) -> None:
        self._conn.close()


def _row(cols: tuple[str, ...], r: tuple) -> dict[str, Any]:
    return dict(zip(cols, r))
