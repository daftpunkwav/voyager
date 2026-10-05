"""Guard the hoisted plain-literal SELECT statement against column drift.

The store maps rows with dict(zip(_ALL_COLS, row)), so a literal column
list that drifts from the tuple (e.g. after an ALTER adds a column) would
silently mislabel values. The constant-level test pins the literal to the
tuple; the recording test additionally pins the statement the store
actually executes to the hoisted constant, so a callsite that bypasses the
constant cannot drift undetected.
"""

import sqlite3
from pathlib import Path
from typing import Any

from notes.store import _ALL_COLS, _SQL_GET_NOTE, NoteStore


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


def test_sql_get_note_columns_match_all_cols() -> None:
    head = _SQL_GET_NOTE.split(" FROM ", 1)[0]
    assert tuple(head.removeprefix("SELECT ").split(", ")) == _ALL_COLS


def test_get_executes_the_locked_statement(tmp_path: Path) -> None:
    store = NoteStore(tmp_path / "t.db")
    recording = _RecordingConn(store._conn)
    store._conn = recording  # type: ignore[assignment]
    assert store.get("missing") is None
    assert recording.executed == [_SQL_GET_NOTE]
