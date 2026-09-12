"""Session search index: lazy catch_up folds conversation events from the
log into FTS, queries are phrase-quoted (model text is data, not grammar),
and a deleted index rebuilds from the log."""

from __future__ import annotations

from agent.runtime.session_index import SessionIndex, phrase_quote
from platform_contracts import ActorKind, ActorRef, DomainEvent, Event
from platform_eventbus import EventLog


def _append(log: EventLog, etype: str, session: str, text: str) -> None:
    log.append(
        Event(
            type=etype,
            actor=ActorRef(kind=ActorKind.USER, id="user"),
            payload={"content": text, "session": session},
        )
    )


def _fresh(tmp_path):
    log = EventLog(tmp_path / "events.db")
    return log


def test_catch_up_and_search_roundtrip(tmp_path) -> None:
    log = _fresh(tmp_path)
    _append(log, DomainEvent.USER_MESSAGE, "s1", "部署 voyager 图谱服务的手记")
    _append(log, DomainEvent.AGENT_MESSAGE, "s1", "已部署完成")
    index = SessionIndex(tmp_path / "idx.db", log)
    try:
        added = index.catch_up()
        assert added == 2
        assert index.catch_up() == 0  # idempotent
        hits = index.search("图谱服务")
        assert hits and hits[0]["session"] == "s1" and hits[0]["role"] == "user"
        assert "图谱" in hits[0]["snippet"]
    finally:
        index.close()
        log.close()


def test_deleted_index_rebuilds_from_log(tmp_path) -> None:
    log = _fresh(tmp_path)
    _append(log, DomainEvent.USER_MESSAGE, "s1", "周报草稿在哪")
    index = SessionIndex(tmp_path / "idx.db", log)
    index.catch_up()
    index.close()
    (tmp_path / "idx.db").unlink()
    index2 = SessionIndex(tmp_path / "idx.db", log)
    try:
        assert index2.catch_up() == 1
        assert index2.search("周报草稿")
    finally:
        index2.close()
        log.close()


def test_query_grammar_is_neutralized(tmp_path) -> None:
    """FTS control syntax in the query must be treated as literal text."""
    log = _fresh(tmp_path)
    _append(log, DomainEvent.USER_MESSAGE, "s1", "plain notes about sqlite")
    index = SessionIndex(tmp_path / "idx.db", log)
    try:
        index.catch_up()
        # A raw FTS5 query expression would raise or match structurally; the
        # phrase-quoted version just finds nothing (the text is not present)
        assert index.search("sqlite OR (deploy NEAR)") == []
        assert index.search('"unbalanced phrase') == []
        assert index.search("sqlite")  # the honest match still works
    finally:
        index.close()
        log.close()


def test_empty_query_returns_nothing(tmp_path) -> None:
    log = _fresh(tmp_path)
    index = SessionIndex(tmp_path / "idx.db", log)
    try:
        assert index.search("") == []
        assert index.search("   ") == []
    finally:
        index.close()
        log.close()


def test_phrase_quote_neutralizes_grammar() -> None:
    """Each term becomes a quoted phrase; operators/quotes are inert data."""
    assert phrase_quote('deploy" OR "hack') == '"deploy" "OR" "hack"'
    assert phrase_quote("sqlite") == '"sqlite"'
    assert phrase_quote("周报") == '"周 报"'
