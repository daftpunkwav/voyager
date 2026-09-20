"""observe capability: the agent's operational self-observation — one action
parameter covers events/quota.

events reads recent platform events from the shared event log (same source
as the activity page); types outside the allowlist are refused so the agent
cannot use it as a generic log dump. quota reports today's token usage,
estimated cost, and the daily quota limit. The agent's observe tool binds
this same capability.
"""

from __future__ import annotations

import json
from typing import Any

from platform_capability import Registry, capability
from platform_contracts import DomainEvent, Event

from agent.capabilities.deps import CapabilityDeps

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


def _events(log: Any, types: list[str] | None, after_seq: int, limit: int) -> dict:
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


def _quota(deps: CapabilityDeps) -> dict:
    """Today's token usage, estimated cost, and the daily quota.

    - tokens_used_today: same semantics as Meter.tokens_used_today; UTC
      calendar day rollover, input+output combined;
    - daily_tokens: hot-read from agent.resource.daily_tokens, 0 = unlimited;
    - cost_usd: estimate from the static price table plus
      agent.pricing.overrides; "unknown" lists models with no price - their
      tokens are NOT counted as zero cost;
    - no percentage/over-quota derivation is computed here; presentation
      choices are left to the frontend.
    """
    limit = int(deps.settings.get("agent.resource.daily_tokens") or 0)
    used = deps.meter.tokens_used_today()
    cost = deps.meter.cost_today()
    return {
        "tokens_used_today": used,
        "daily_tokens": limit,
        "cost_usd": cost["cost_usd"],
        "cost_unknown_models": cost["unknown"],
    }


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="observe",
        description=(
            "Operational self-observation: action events (types within the "
            "allowlist, after_seq for incremental reads, limit) and quota "
            "(today's token usage, cost, daily limit)"
        ),
    )
    def observe(
        action: str,
        types: list[str] | None = None,
        after_seq: int = 0,
        limit: int = _DEFAULT_LIMIT,
    ) -> dict:
        if action == "events":
            return _events(deps.log, types, after_seq, limit)
        if action == "quota":
            return _quota(deps)
        from platform_contracts import ErrorSuffix, ServiceError

        raise ServiceError(
            "agent",
            ErrorSuffix.INVALID_INPUT,
            f"unknown action: {action!r}",
            hint="valid actions: events/quota",
        )
