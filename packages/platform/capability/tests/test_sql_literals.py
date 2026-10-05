"""Guard the hoisted plain-literal SELECT statement against column drift.

The store maps rows with dict(zip(_COLS, row)), so a literal column list
that drifts from the tuple (e.g. after an ALTER adds a column) would
silently mislabel values. The constant-level test pins the literal to the
tuple; the recording test additionally pins the query the sink actually
executes to the hoisted head, so a callsite that bypasses the constant
cannot drift undetected.
"""

import sqlite3
from pathlib import Path
from typing import Any

from platform_capability.audit_db import _COLS, _SQL_RECENT_HEAD, SqliteAuditSink


class _RecordingConn:
    """Connection wrapper that records executed SQL while delegating to sqlite3."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._real = conn
        self.executed: list[str] = []

    def execute(self, sql: str, *args: Any) -> Any:
        self.executed.append(sql)
        return self._real.execute(sql, *args)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def test_sql_recent_head_columns_match_cols() -> None:
    head = _SQL_RECENT_HEAD.split(" FROM ", 1)[0]
    assert tuple(head.removeprefix("SELECT ").split(", ")) == _COLS


def test_recent_executes_the_locked_head(tmp_path: Path) -> None:
    sink = SqliteAuditSink(tmp_path / "t.db")
    recording = _RecordingConn(sink._conn)
    sink._conn = recording  # type: ignore[assignment]
    assert sink.recent(limit=1) == []
    assert len(recording.executed) == 1
    assert recording.executed[0].startswith(_SQL_RECENT_HEAD)
