"""Session surface actions: search folds the log lazily and returns snippets;
trace follows fork lineage (ancestors up, children down); read pages history
from the shared event log. All go through session_action (the shared dispatch
the capability and the aggregated tool both bind)."""

from __future__ import annotations

from agent.build import build_agent
from agent.llm import FakeLLM
from agent.runtime.session_index import SessionIndex
from agent.tools.session.actions import session_action
from platform_contracts import ActorKind, ActorRef, DomainEvent, Event
from platform_eventbus import EventLog

_SYSTEM = ActorRef(kind=ActorKind.SYSTEM, id="test")


def _app(tmp_path):
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
    return app


def _seed(log: EventLog, session: str, text: str) -> None:
    log.append(
        Event(
            type=DomainEvent.USER_MESSAGE,
            actor=ActorRef(kind=ActorKind.USER, id="user"),
            payload={"content": text, "session": session},
        )
    )


async def test_search_folds_and_finds(tmp_path) -> None:
    app = _app(tmp_path)
    try:
        _seed(app.log, "s1", "把本周新增资料整理成笔记")
        _seed(app.log, "s2", "部署缓存服务")
        index = SessionIndex(tmp_path / "sidx.db", app.log)
        out = session_action(app.master.sessions, index, action="search", query="整理 笔记")
        assert isinstance(out, list) and out[0]["session"] == "s1"
        assert "笔记" in out[0]["snippet"]
        miss = session_action(app.master.sessions, index, action="search", query="")
        assert "参数错误" in str(miss)
    finally:
        app.close()


async def test_trace_follows_fork_lineage(tmp_path) -> None:
    app = _app(tmp_path)
    try:
        mgr = app.master.sessions
        parent = mgr.create(title="main")["session_id"]
        child = mgr.fork(parent, title="branch")["session_id"]
        out = session_action(mgr, action="trace", session_id=child)
        assert out["ancestors"] == [parent]
        siblings = session_action(mgr, action="trace", session_id=parent)
        assert child in siblings["children"]
        from platform_contracts import ServiceError

        try:
            session_action(mgr, action="trace", session_id="nope")
            raised = False
        except ServiceError:
            raised = True
        assert raised
    finally:
        app.close()


async def test_read_pages_history(tmp_path) -> None:
    app = _app(tmp_path)
    try:
        for i in range(5):
            _seed(app.log, "s1", f"message {i}")
        out = session_action(app.master.sessions, log=app.log, action="read", session_id="s1")
        assert out["session_id"] == "s1"
        assert [m["text"] for m in out["messages"]] == [f"message {i}" for i in range(5)]
        assert out["has_more"] is False
        paged = session_action(
            app.master.sessions, log=app.log, action="read", session_id="s1", limit=2
        )
        assert len(paged["messages"]) == 2 and paged["has_more"] is True
    finally:
        app.close()


async def test_unknown_action_rejects(tmp_path) -> None:
    from platform_contracts import ServiceError

    app = _app(tmp_path)
    try:
        try:
            session_action(app.master.sessions, action="explode")
            raised = False
        except ServiceError:
            raised = True
        assert raised
    finally:
        app.close()
