"""read_events tool: read recent platform events from the shared event log
(same data source as the activity page), filtered by an allowlist of types.

Agent-only by design: the human reads the feed through the activity
transport. Types outside the allowlist are refused so the agent cannot use
this as a generic log dump; payloads are truncated per row.
"""

from __future__ import annotations

import json
from typing import Any

from platform_contracts import DomainEvent, Event
from platform_eventbus import EventLog

from agent.tools.core.base import AgentTool

#: Types the agent may read back. Glob patterns (task.*) are accepted as-is by
#: the log; concrete types must be in this set. agent.delta (streaming chunks)
#: and agent.ask (dialog internals) are excluded as noise.
_READABLE_TYPES: frozenset[str] = frozenset(
    {
        DomainEvent.USER_MESSAGE,
        DomainEvent.USER_ONLINE,
        DomainEvent.USER_ACTIVITY,
        DomainEvent.TASK_ENQUEUED,
        DomainEvent.TASK_PROGRESS,
        DomainEvent.TASK_COMPLETED,
        DomainEvent.TASK_FAILED,
        "task.*",
        DomainEvent.AGENT_MESSAGE,
        DomainEvent.AGENT_STEP,
        DomainEvent.AGENT_POLICY_NOTIFY,
        DomainEvent.AGENT_NAVIGATE,
        DomainEvent.NOTE_CREATED,
        DomainEvent.SOURCE_ADDED,
        DomainEvent.SOURCE_READY,
        DomainEvent.SOURCE_REMOVED,
        DomainEvent.SETTINGS_CHANGED,
        DomainEvent.SERVICE_HEALTH_CHANGED,
    }
)
_DEFAULT_TYPES = (
    DomainEvent.TASK_COMPLETED,
    DomainEvent.TASK_FAILED,
    DomainEvent.SERVICE_HEALTH_CHANGED,
    DomainEvent.SETTINGS_CHANGED,
)
_DEFAULT_LIMIT = 30
_MAX_LIMIT = 200
_MAX_PAYLOAD = 600


def _row(seq: int, event: Event) -> dict[str, Any]:
    payload = json.dumps(event.payload, ensure_ascii=False, default=str)
    if len(payload) > _MAX_PAYLOAD:
        payload = payload[:_MAX_PAYLOAD] + "…"
    return {
        "seq": seq,
        "type": event.type,
        "ts": event.ts,
        "actor": f"{event.actor.kind.value}:{event.actor.id}" if event.actor else "",
        "payload": payload,
    }


def read_events_tool(log: EventLog) -> AgentTool:
    def read_events(
        types: list[str] | None = None, after_seq: int = 0, limit: int = _DEFAULT_LIMIT
    ) -> dict:
        wanted = tuple(types) if types else _DEFAULT_TYPES
        unknown = [t for t in wanted if t not in _READABLE_TYPES]
        if unknown:
            return {
                "error": f"[参数错误] 不可读取的事件类型: {', '.join(unknown)}",
                "readable": sorted(_READABLE_TYPES),
            }
        try:
            cap = max(1, min(int(limit), _MAX_LIMIT))
            start = max(0, int(after_seq))
        except (TypeError, ValueError):
            return {"error": "[参数错误] after_seq / limit 需要整数"}
        if start > 0:
            rows = log.read_after(after_seq=start, types=wanted, limit=cap)
        else:
            rows = log.read_before(before_seq=log.latest_seq() + 1, types=wanted, limit=cap)
        return {
            "events": [_row(s, e) for s, e in rows],
            "latest_seq": rows[-1][0] if rows else start,
        }

    return AgentTool(
        name="read_events",
        description=(
            "读取最近的平台事件(任务完成/失败、服务健康变化、设置变更等,与活动页同源);"
            "types 限定类型,after_seq 从某序号之后增量读取;用于了解后台发生了什么"
        ),
        handler=read_events,
        dimension="none",
        concurrent_safe=True,
        schema={
            "type": "object",
            "properties": {
                "types": {"type": "array", "items": {"type": "string"}},
                "after_seq": {"type": "integer"},
                "limit": {"type": "integer"},
            },
        },
    )


__all__ = ["read_events_tool"]
