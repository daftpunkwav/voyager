"""read_history tool: page a chat session's message history backward from
the event log (same rows the chat page shows; before_seq pages older).

Agent-only by design: the human reads history through the chat transport.
Reads user.message / agent.message rows filtered by session; a session
filter scans the log in bounded chunks toward older rows until `limit`
matches are collected, so `has_more` stays honest.
"""

from __future__ import annotations

from typing import Any

from platform_contracts import DomainEvent, Event
from platform_eventbus import EventLog

from agent.tools.core.base import AgentTool

SessionManagerLike = Any  # agent.master.sessions.SessionManager (duck-typed)

_HISTORY_TYPES = (DomainEvent.USER_MESSAGE, DomainEvent.AGENT_MESSAGE)
_DEFAULT_LIMIT = 40
_MAX_LIMIT = 200
_CHUNK = 400
_MAX_TEXT = 2000


def _row(seq: int, event: Event) -> dict[str, Any]:
    text = str(event.payload.get("content") or "")
    if len(text) > _MAX_TEXT:
        text = text[:_MAX_TEXT] + "…[截断]"
    return {"seq": seq, "type": event.type, "ts": event.ts, "text": text}


def read_history_tool(log: EventLog, manager: SessionManagerLike) -> AgentTool:
    def read_history(
        session_id: str = "", before_seq: int = 0, limit: int = _DEFAULT_LIMIT
    ) -> dict:
        session = str(session_id or manager.active_id() or "")
        if not session:
            return {"session_id": "", "messages": [], "has_more": False}
        try:
            cap = max(1, min(int(limit), _MAX_LIMIT))
        except (TypeError, ValueError):
            return {"error": "[参数错误] limit 需要整数"}
        cursor = int(before_seq) if before_seq and int(before_seq) > 0 else log.latest_seq() + 1
        matched: list[tuple[int, Event]] = []
        while len(matched) <= cap:
            rows = log.read_before(before_seq=cursor, types=_HISTORY_TYPES, limit=_CHUNK)
            if not rows:
                break
            cursor = rows[0][0]
            matched[:0] = [
                (s, e) for s, e in rows if str(e.payload.get("session") or "") == session
            ]
        has_more = len(matched) > cap
        page = matched[-cap:] if has_more else matched
        return {
            "session_id": session,
            "messages": [_row(s, e) for s, e in page],
            "has_more": has_more,
            "oldest_seq": page[0][0] if page else 0,
        }

    return AgentTool(
        name="read_history",
        description=(
            "分页读取某个会话(默认当前会话)的消息历史,最新在后;"
            "before_seq 传上一页 oldest_seq 继续往前翻;用于回顾更早的对话而不占用常驻上下文"
        ),
        handler=read_history,
        dimension="none",
        concurrent_safe=True,
        schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "before_seq": {"type": "integer"},
                "limit": {"type": "integer"},
            },
        },
    )


__all__ = ["read_history_tool"]
