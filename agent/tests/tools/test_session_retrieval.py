"""Session retrieval tools: search folds the log lazily and returns snippets;
trace follows fork lineage (ancestors up, children down)."""

from __future__ import annotations

from agent.build import build_agent
from agent.llm import FakeLLM
from agent.runtime.session_index import SessionIndex
from agent.tools.observe import session_retrieval_tools
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
        tools = session_retrieval_tools(index, app.master.sessions)
        out = await tools["session_search"].handler(query="整理 笔记")
        assert isinstance(out, list) and out[0]["session"] == "s1"
        assert "笔记" in out[0]["snippet"]
        miss = await tools["session_search"].handler(query="")
        assert "参数错误" in str(miss)
    finally:
        app.close()


async def test_trace_follows_fork_lineage(tmp_path) -> None:
    app = _app(tmp_path)
    try:
        mgr = app.master.sessions
        parent = mgr.create(title="main")["session_id"]
        child = mgr.fork(parent, title="branch")["session_id"]
        tools = session_retrieval_tools(SessionIndex(tmp_path / "sidx.db", app.log), mgr)
        out = await tools["session_trace"].handler(session_id=child)
        assert out["ancestors"] == [parent]
        siblings = await tools["session_trace"].handler(session_id=parent)
        assert child in siblings["children"]
        from platform_contracts import ServiceError

        try:
            await tools["session_trace"].handler(session_id="nope")
            raised = False
        except ServiceError:
            raised = True
        assert raised
    finally:
        app.close()
