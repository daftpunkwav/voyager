"""Guard the hoisted plain-literal SELECT statements against column drift.

The store maps rows with dict(zip(_COLS, row)), so a literal column list
that drifts from the tuple (e.g. after an ALTER adds a column) would
silently mislabel values. These tests pin the literal to the tuple.
"""

from office.store import _COLS, _SQL_GET_DOC, _SQL_LIST_HEAD


def _select_columns(sql: str) -> tuple[str, ...]:
    return tuple(sql.split(" FROM ", 1)[0].removeprefix("SELECT ").split(", "))


def test_sql_get_doc_columns_match_cols() -> None:
    assert _select_columns(_SQL_GET_DOC) == _COLS


def test_sql_list_head_columns_match_cols() -> None:
    assert _select_columns(_SQL_LIST_HEAD) == _COLS
