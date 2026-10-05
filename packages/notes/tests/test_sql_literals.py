"""Guard the hoisted plain-literal SELECT statement against column drift.

The store maps rows with dict(zip(_ALL_COLS, row)), so a literal column
list that drifts from the tuple (e.g. after an ALTER adds a column) would
silently mislabel values. This test pins the literal to the tuple.
"""

from notes.store import _ALL_COLS, _SQL_GET_NOTE


def test_sql_get_note_columns_match_all_cols() -> None:
    head = _SQL_GET_NOTE.split(" FROM ", 1)[0]
    assert tuple(head.removeprefix("SELECT ").split(", ")) == _ALL_COLS
