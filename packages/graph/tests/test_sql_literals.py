"""Guard the plain-literal SELECT statements in columns.py against column
drift from _NODE_COLS / _EDGE_COLS.

store.py and operations.py map rows with dict(zip(_NODE_COLS/_EDGE_COLS,
row)), so a literal column list that drifts from the tuples would silently
mislabel values. These tests pin every literal to its tuple.
"""

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
