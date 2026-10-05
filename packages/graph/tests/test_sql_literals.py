"""Guard the plain-literal SELECT statements in columns.py against column
drift from _NODE_COLS / _EDGE_COLS.

store.py and operations.py map rows with dict(zip(_NODE_COLS/_EDGE_COLS,
row)), so a literal column list that drifts from the tuples would silently
mislabel values. The constant-level tests pin every literal to its tuple;
the recording test additionally pins the statements the store actually
executes on its read paths to the hoisted constants, so a callsite that
bypasses the constants cannot drift undetected.
"""

import sqlite3
from pathlib import Path
from typing import Any

from graph.columns import (
    _EDGE_COLS,
    _NODE_COLS,
    _SQL_CROSS_EDGES,
    _SQL_EDGES_BY_PROJECT,
    _SQL_GET_EDGE_BY_ID,
    _SQL_GET_EDGE_BY_PROJECT_ID,
    _SQL_GET_NODE_BY_ID,
    _SQL_GET_NODE_BY_KEY,
)
from graph.store import GraphStore


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


def test_node_literals_match_node_cols() -> None:
    for sql in (_SQL_GET_NODE_BY_KEY, _SQL_GET_NODE_BY_ID):
        assert _select_columns(sql) == _NODE_COLS


def test_edge_literals_match_edge_cols() -> None:
    for sql in (
        _SQL_GET_EDGE_BY_ID,
        _SQL_GET_EDGE_BY_PROJECT_ID,
        _SQL_EDGES_BY_PROJECT,
        _SQL_CROSS_EDGES,
    ):
        assert _select_columns(sql) == _EDGE_COLS


def test_store_reads_execute_the_locked_statements(tmp_path: Path) -> None:
    store = GraphStore(tmp_path / "t.db")
    recording = _RecordingConn(store._conn)
    store._conn = recording  # type: ignore[assignment]
    assert store.get_node("p", "l", "q") is None
    assert store._node_by_id("p", "n1") is None
    assert store._edge_by_id("p", "e1") is None
    assert recording.executed == [
        _SQL_GET_NODE_BY_KEY,
        _SQL_GET_NODE_BY_ID,
        _SQL_GET_EDGE_BY_PROJECT_ID,
    ]
