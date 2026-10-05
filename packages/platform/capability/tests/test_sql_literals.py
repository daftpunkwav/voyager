"""Guard the hoisted plain-literal SELECT statement against column drift.

The store maps rows with dict(zip(_COLS, row)), so a literal column list
that drifts from the tuple (e.g. after an ALTER adds a column) would
silently mislabel values. This test pins the literal to the tuple.
"""

from platform_capability.audit_db import _COLS, _SQL_RECENT_HEAD


def test_sql_recent_head_columns_match_cols() -> None:
    head = _SQL_RECENT_HEAD.split(" FROM ", 1)[0]
    assert tuple(head.removeprefix("SELECT ").split(", ")) == _COLS
