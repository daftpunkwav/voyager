"""Guard the hoisted plain-literal SELECT statements against column drift.

The stores map rows with dict(zip(_COLS, row)), so a literal column list
that drifts from the tuple (e.g. after an ALTER adds a column) would
silently mislabel values. The constant-level tests pin each literal to its
tuple; the recording test additionally pins the query the doc store
actually executes to the hoisted head, so a callsite that bypasses the
constant cannot drift undetected.
"""

import sqlite3
from pathlib import Path
from typing import Any

from sources.modules.doc.store import _COLS as _DOC_COLS
from sources.modules.doc.store import _SQL_GET_DOC as _DOC_SQL_GET
from sources.modules.doc.store import _SQL_SUMMARY_HEAD as _DOC_SQL_HEAD
from sources.modules.doc.store import DocStore
from sources.modules.repo.store import _COLS as _REPO_COLS
from sources.modules.repo.store import _SQL_FULL_HEAD as _REPO_SQL_FULL
from sources.modules.repo.store import _SQL_GET_BY_ID_FULL as _REPO_SQL_GET_FULL
from sources.modules.repo.store import _SQL_GET_BY_ID_SUMMARY as _REPO_SQL_GET_SUMMARY
from sources.modules.repo.store import _SQL_GET_BY_URL as _REPO_SQL_GET_URL
from sources.modules.repo.store import _SQL_SUMMARY_HEAD as _REPO_SQL_HEAD
from sources.modules.repo.store import _SUMMARY_COLS as _REPO_SUMMARY_COLS
from sources.modules.web.store import _COLS as _WEB_COLS
from sources.modules.web.store import _LIST_COLS as _WEB_LIST_COLS
from sources.modules.web.store import _SQL_GET_PAGE as _WEB_SQL_GET
from sources.modules.web.store import _SQL_LIST_HEAD as _WEB_SQL_LIST
from sources.modules.web.store import _SQL_SUMMARY_HEAD as _WEB_SQL_HEAD


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


def _head_of(sql: str, marker: str = " FROM ") -> tuple[str, ...]:
    head = sql.split(marker, 1)[0]
    return tuple(head.removeprefix("SELECT ").split(", "))


def test_doc_sql_heads_columns_match_cols() -> None:
    assert _head_of(_DOC_SQL_HEAD) == _DOC_COLS
    assert _head_of(_DOC_SQL_GET) == _DOC_COLS
    assert _DOC_SQL_GET.startswith(_DOC_SQL_HEAD)


def test_repo_sql_heads_columns_match_cols() -> None:
    assert _head_of(_REPO_SQL_HEAD) == _REPO_SUMMARY_COLS
    assert _head_of(_REPO_SQL_FULL) == _REPO_COLS
    assert _REPO_SQL_GET_FULL.startswith(_REPO_SQL_FULL)
    assert _REPO_SQL_GET_SUMMARY.startswith(_REPO_SQL_HEAD)
    assert _REPO_SQL_GET_URL.startswith(_REPO_SQL_HEAD)


def test_web_sql_heads_columns_match_cols() -> None:
    assert _head_of(_WEB_SQL_LIST) == _WEB_LIST_COLS
    assert _head_of(_WEB_SQL_HEAD) == _WEB_LIST_COLS + ("updated_ts",)
    assert _head_of(_WEB_SQL_GET) == _WEB_COLS


def test_get_executes_the_locked_head(tmp_path: Path) -> None:
    store = DocStore(tmp_path / "t.db")
    recording = _RecordingConn(store._conn)
    store._conn = recording  # type: ignore[assignment]
    assert store.get("missing") is None
    assert len(recording.executed) == 1
    assert recording.executed[0].startswith(_DOC_SQL_HEAD)
