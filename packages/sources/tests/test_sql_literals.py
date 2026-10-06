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
from sources.modules.repo.store import RepoStore
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


# The lookup literals spelled out independently of the store constants, so a
# predicate that drifts from exact equality (e.g. LIKE) fails these pins.
_EXPECTED_DOC_GET = (
    "SELECT id, title, filename, ext, local_path, category, tags, progress,"
    " note, status, error, source, added_ts, updated_ts FROM documents"
    " WHERE id = ?"
)
_EXPECTED_REPO_GET_FULL = (
    "SELECT id, owner, name, url, description, stars, language, category,"
    " tags, progress, note, local_path, readme, status, error, source,"
    " added_ts, updated_ts FROM repos WHERE id = ?"
)
_EXPECTED_REPO_GET_SUMMARY = (
    "SELECT id, owner, name, url, description, stars, language, category,"
    " tags, progress, note, local_path, status, error, source, added_ts,"
    " updated_ts FROM repos WHERE id = ?"
)
_EXPECTED_REPO_GET_URL = (
    "SELECT id, owner, name, url, description, stars, language, category,"
    " tags, progress, note, local_path, status, error, source, added_ts,"
    " updated_ts FROM repos WHERE url = ?"
)
_EXPECTED_WEB_GET = (
    "SELECT id, title, url, domain, summary, content, tags, category, meta,"
    " added_ts, updated_ts FROM webpages WHERE id = ?"
)


def test_lookup_sql_is_exact_equality() -> None:
    assert _DOC_SQL_GET == _EXPECTED_DOC_GET
    assert _REPO_SQL_GET_FULL == _EXPECTED_REPO_GET_FULL
    assert _REPO_SQL_GET_SUMMARY == _EXPECTED_REPO_GET_SUMMARY
    assert _REPO_SQL_GET_URL == _EXPECTED_REPO_GET_URL
    assert _WEB_SQL_GET == _EXPECTED_WEB_GET


def test_lookups_match_only_the_exact_key(tmp_path: Path) -> None:
    """Wildcard-shaped keys must not match through the id/url predicates."""
    doc_store = DocStore(tmp_path / "doc.db")
    doc_store.add({"id": "a%", "title": "pct"})
    doc_store.add({"id": "a_", "title": "under"})
    doc_pct = doc_store.get("a%")
    doc_under = doc_store.get("a_")
    assert doc_pct is not None and doc_pct["title"] == "pct"
    assert doc_under is not None and doc_under["title"] == "under"
    repo_store = RepoStore(tmp_path / "repo.db")
    repo_store.add({"id": "a%", "name": "pct", "url": "u%"})
    repo_store.add({"id": "a_", "name": "under", "url": "u_"})
    repo_pct = repo_store.get("a%")
    repo_under = repo_store.get("a_")
    url_pct = repo_store.get_by_url("u%")
    url_under = repo_store.get_by_url("u_")
    assert repo_pct is not None and repo_pct["name"] == "pct"
    assert repo_under is not None and repo_under["name"] == "under"
    assert url_pct is not None and url_pct["name"] == "pct"
    assert url_under is not None and url_under["name"] == "under"


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


def test_get_executes_the_locked_literal(tmp_path: Path) -> None:
    store = DocStore(tmp_path / "t.db")
    first = store.add({"title": "first"})
    store.add({"title": "second"})
    recording = _RecordingConn(store._conn)
    store._conn = recording  # type: ignore[assignment]
    assert store.get("missing") is None
    hit = store.get(first)
    assert hit is not None and hit["title"] == "first"
    # Exact-literal pin: a statement that drops the WHERE id = ? predicate
    # would otherwise pass a startswith(head) check and return the first row.
    assert recording.executed == [_DOC_SQL_GET, _DOC_SQL_GET]
