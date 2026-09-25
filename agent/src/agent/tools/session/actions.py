"""Session surface dispatch: one action function for the whole chat-session
domain, plus the agent-side interaction guard.

The human REST capability and the agent's session tool both bind
`session_action` — one implementation, two drivers (the todowrite pattern).
Actor-sensitive invariants are interaction integrity, not privacy, so they
live in `agent_surface_guard` and are enforced only on the agent path (the
capability_tool guard hook): the human page may rename/delete/switch the
session it is looking at, the agent may not change the user's view.

Actions:
    list / create / fork / rename / delete / get / read / search /
    trace / pin / archive / set_active
"""

from __future__ import annotations

from typing import Any

from platform_contracts import ErrorSuffix, ServiceError

SessionManagerLike = Any  # agent.orchestrator.sessions.SessionManager (duck-typed)
SessionIndexLike = Any  # agent.runtime.session_index.SessionIndex (duck-typed)
EventLogLike = Any  # platform_eventbus.EventLog (duck-typed)

#: History paging constants (ported from the former read_history tool).
_HISTORY_TYPES_DEFAULT_LIMIT = 40
_MAX_LIMIT = 200
_CHUNK = 400
_MAX_TEXT = 2000

#: Model-facing action table (compact; the schema stays flat strings).
ACTION_TABLE = (
    "list(无参)/ create(title)/ fork(source_session_id,title)/"
    " rename(session_id,title)/ delete(session_id,不可逆)/ get(session_id,持久快照含历史)/"
    " read(session_id,before_seq,limit,分页,传上页 oldest_seq 往前翻)/"
    " search(query,limit,全文检索历史会话)/ trace(session_id,分支血缘)/"
    " pin(session_id,pinned)/ archive(session_id,archived)/ set_active(session_id,人类专属)"
)


def session_action(
    sessions: SessionManagerLike,
    index: SessionIndexLike | None = None,
    log: EventLogLike | None = None,
    *,
    action: str,
    session_id: str = "",
    title: str = "",
    source_session_id: str = "",
    persona: str = "orchestrator",
    keep_messages: int = 0,
    before_seq: int = 0,
    limit: int = 0,
    query: str = "",
    pinned: bool = True,
    archived: bool = True,
) -> Any:
    """Dispatch one session action against the shared SessionManager."""
    if action == "list":
        return {"sessions": sessions.list(), "active": sessions.active_id()}
    if action == "create":
        return sessions.create(title=title.strip()[:40], persona=persona)
    if action == "fork":
        return sessions.fork(
            source_session_id, title=title.strip()[:40], keep_messages=max(0, keep_messages)
        )
    if action == "rename":
        sessions.rename(session_id, title.strip()[:40])
        return {"session_id": session_id, "title": title.strip()[:40]}
    if action == "delete":
        return sessions.delete(session_id)
    if action == "get":
        snap = sessions.snapshot(session_id)
        if snap is None:
            return {"session_id": session_id, "found": False}
        return {"found": True, **snap.to_dict()}
    if action == "read":
        return _read_history(
            sessions, log, session_id=session_id, before_seq=before_seq, limit=limit
        )
    if action == "search":
        return _search(index, query=query, limit=limit)
    if action == "trace":
        return sessions.lineage(session_id)
    if action == "pin":
        return sessions.set_flags(session_id, pinned=pinned)
    if action == "archive":
        return sessions.set_flags(session_id, archived=archived)
    if action == "set_active":
        return sessions.set_active(session_id)
    raise ServiceError(
        "agent",
        ErrorSuffix.INVALID_INPUT,
        f"unknown action: {action!r}",
        hint="valid actions: list/create/fork/rename/delete/get/read/search/trace/pin/archive/set_active",
    )


def agent_surface_guard(sessions: SessionManagerLike, args: dict[str, Any]) -> str | None:
    """Agent-side preconditions (interaction integrity): the agent never
    changes the conversation the user is looking at. Returns a refusal text
    or None to proceed; the human path never runs this."""
    action = str(args.get("action") or "")
    if action == "set_active":
        return "[已拒绝] 切换用户正在看的会话是用户自己的操作;请告知用户切换,或用 session_create 新建会话"
    if action in ("rename", "delete") and str(args.get("session_id") or "") == str(
        sessions.active_id() or ""
    ):
        what = "重命名" if action == "rename" else "删除"
        return f"[已拒绝] 不能{what}用户当前正在看的会话;请让用户自己操作"
    return None


def _read_history(
    sessions: SessionManagerLike,
    log: EventLogLike | None,
    *,
    session_id: str,
    before_seq: int,
    limit: int,
) -> dict[str, Any]:
    """Page a session's message history backward from the event log (ported
    from the former read_history tool; has_more stays honest via bounded
    chunk scans toward older rows)."""
    from platform_contracts import DomainEvent, Event

    history_types = (DomainEvent.USER_MESSAGE, DomainEvent.AGENT_MESSAGE)
    session = str(session_id or sessions.active_id() or "")
    if not session:
        return {"session_id": "", "messages": [], "has_more": False}
    if log is None:
        return {"session_id": session, "messages": [], "has_more": False}
    try:
        cap = max(1, min(int(limit) if limit else _HISTORY_TYPES_DEFAULT_LIMIT, _MAX_LIMIT))
    except (TypeError, ValueError):
        return {"error": "[参数错误] limit 需要整数"}
    cursor = int(before_seq) if before_seq and int(before_seq) > 0 else log.latest_seq() + 1
    matched: list[tuple[int, Event]] = []
    while len(matched) <= cap:
        rows = log.read_before(before_seq=cursor, types=history_types, limit=_CHUNK)
        if not rows:
            break
        cursor = rows[0][0]
        matched[:0] = [(s, e) for s, e in rows if str(e.payload.get("session") or "") == session]
    has_more = len(matched) > cap
    page = matched[-cap:] if has_more else matched

    def _row(seq: int, event: Event) -> dict[str, Any]:
        text = str(event.payload.get("content") or "")
        if len(text) > _MAX_TEXT:
            text = text[:_MAX_TEXT] + "…[截断]"
        return {"seq": seq, "type": event.type, "ts": event.ts, "text": text}

    return {
        "session_id": session,
        "messages": [_row(s, e) for s, e in page],
        "has_more": has_more,
        "oldest_seq": page[0][0] if page else 0,
    }


def _search(index: SessionIndexLike | None, *, query: str, limit: int) -> Any:
    """Full-text search over past conversations (ported from the former
    session_search tool). Query text is data — phrase-quoted, never search
    grammar."""
    if index is None:
        return "[参数错误] 会话检索索引未装配"
    needle = str(query or "").strip()
    if not needle:
        return "[参数错误] query 不能为空"
    index.catch_up()  # lazy fold: the index stays current without a live subscription
    hits = index.search(needle, limit=max(1, min(int(limit) if limit else 8, 50)))
    if not hits:
        return f"未找到与「{needle[:80]}」相关的历史会话内容"
    return hits


__all__ = ["ACTION_TABLE", "agent_surface_guard", "session_action"]
