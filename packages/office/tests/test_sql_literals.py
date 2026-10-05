"""Guard the hoisted plain-literal SELECT statements against column drift.

The store maps rows with dict(zip(_COLS, row)), so a literal column list
that drifts from the tuple (e.g. after an ALTER adds a column) would
silently mislabel values. The constant-level tests pin each literal to the
tuple; the recording test additionally pins the statements the store
actually executes to the hoisted constants, so a callsite that bypasses
the constants cannot drift undetected.
"""

import sqlite3
from pathlib import Path
from typing import Any

from office.store import _COLS, _SQL_GET_DOC, _SQL_LIST_HEAD, DocumentStore


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


def _select_columns(sql: str) -> tuple[str, ...]:
    return tuple(sql.split(" FROM ", 1)[0].removeprefix("SELECT ").split(", "))


def test_sql_get_doc_columns_match_cols() -> None:
    assert _select_columns(_SQL_GET_DOC) == _COLS


def test_sql_list_head_columns_match_cols() -> None:
    assert _select_columns(_SQL_LIST_HEAD) == _COLS


def test_reads_execute_the_locked_statements(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path / "t.db")
    recording = _RecordingConn(store._conn)
    store._conn = recording  # type: ignore[assignment]
    assert store.get("missing") is None
    assert store.list() == []
    assert recording.executed[0] == _SQL_GET_DOC
    assert recording.executed[1].startswith(_SQL_LIST_HEAD)
