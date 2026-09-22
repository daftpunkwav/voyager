"""User activity reporting and activity feed endpoints.

Responsibilities:
- POST /api/activity: reports user behavior (page views / pointer /
  selection); the frontend applies the category whitelist and throttling,
  while the gateway only publishes user.activity events without any
  business interpretation. No built-in agent consumer: reports land in the
  event log for the activity page only (declarative hooks may still
  subscribe to user.activity via their own patterns).
- GET /api/activity/feed: data source for the activity page, rebuilt by
  filtering the event log by type; no dedicated business tables.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from platform_contracts import (
    LOCAL_USER,
    ActorKind,
    ActorRef,
    DomainEvent,
    ErrorSuffix,
    Event,
    ServiceError,
)
from platform_eventbus import EventBus

from .ratelimit import RateLimiter

_DOMAIN = "gateway"
_ACTIVITY_KINDS = ("page_view", "pointer", "selection", "manual")  # initial kinds

#: The agent-operations scope (`agent=true`): event types that record a change
#: to the system, plus agent.step narrowed further to the file-writing tools
#: (conversational messages and read-style calls are session work, not
#: operations). Attribution: domain events carry payload.session only when a
#: chat turn drove them; settings.changed distinguishes by the caller's actor.
_OPERATION_TYPES = frozenset(
    {
        DomainEvent.NOTE_CREATED,
        DomainEvent.NOTE_EDITED,
        DomainEvent.NOTE_DELETED,
        DomainEvent.NOTE_RESTORED,
        DomainEvent.NOTE_PURGED,
        DomainEvent.SOURCE_ADDED,
        DomainEvent.SOURCE_REMOVED,
        DomainEvent.SESSION_DELETED,
        DomainEvent.SETTINGS_CHANGED,
        DomainEvent.AGENT_STEP,
    }
)
_WRITE_TOOLS = frozenset({"write", "edit"})


def _is_agent_operation(ev: Event) -> bool:
    """Whether one event records an operation the agent performed on the
    system (as opposed to conversation traffic or the user's own actions)."""
    if ev.type not in _OPERATION_TYPES:
        return False
    if ev.type == DomainEvent.AGENT_STEP:
        payload = ev.payload
        return (
            str(payload.get("kind") or "") == "tool"
            and str(payload.get("name") or "") in _WRITE_TOOLS
            and bool(str(payload.get("session") or ""))
        )
    if ev.type == DomainEvent.SETTINGS_CHANGED:
        # The store stamps the real caller: agent turns publish with the AGENT
        # actor, the settings UI with LOCAL_USER.
        return ev.actor is not None and ev.actor.kind == ActorKind.AGENT
    return bool(str(ev.payload.get("session") or ""))


def build_activity_router(bus: EventBus, limiter: RateLimiter) -> APIRouter:
    router = APIRouter()

    def _actor(request: Request) -> ActorRef:
        return getattr(request.state, "actor", None) or LOCAL_USER

    async def _json_body(request: Request) -> dict:
        """Parse and validate the request body: bad JSON / non-object -> 400, not 500."""
        try:
            body = await request.json()
        except Exception as exc:
            raise ServiceError(
                _DOMAIN, ErrorSuffix.INVALID_INPUT, "Request body must be valid JSON"
            ) from exc
        if not isinstance(body, dict):
            raise ServiceError(
                _DOMAIN, ErrorSuffix.INVALID_INPUT, "Request body must be a JSON object"
            )
        return body

    @router.post("/api/activity")
    async def report_activity(request: Request) -> dict:
        body = await _json_body(request)
        kind = str(body.get("kind") or "")
        if kind not in _ACTIVITY_KINDS:
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.INVALID_INPUT,
                f"unknown activity kind: {kind!r}",
                hint=f"allowed: {list(_ACTIVITY_KINDS)}",
            )
        actor = _actor(request)
        limiter.check(actor.id)
        seq = await bus.publish(
            Event(
                type=DomainEvent.USER_ACTIVITY,
                actor=actor,
                payload={
                    "kind": kind,
                    "page": str(body.get("page") or ""),
                    "detail": dict(body.get("detail") or {}),
                },
            )
        )
        return {"seq": seq}

    @router.get("/api/activity/feed")
    async def activity_feed(
        after_seq: int = 0,
        types: str = "",
        limit: int = 200,
        agent: bool = False,
        session: str = "",
        recent: bool = False,
    ) -> dict:
        """Activity feed. `recent=true` returns the newest `limit` events
        instead of paging forward from after_seq. `agent=true` keeps only
        agent operations (the whitelist above: note/source lifecycle,
        session deletes, agent-driven settings changes, and file writes);
        `session=<id>` narrows to one session's operations (implies agent).
        The type filter still narrows the SQL read; attribution filters in
        memory afterwards, so a heavily filtered page may return fewer rows
        than `limit`."""
        type_list = tuple(t for t in types.split(",") if t) or None
        cap = max(1, min(limit, 1000))

        def _wanted(ev: Event) -> bool:
            if agent and not _is_agent_operation(ev):
                return False
            if session:
                return str(ev.payload.get("session") or "") == session
            return True

        if recent and after_seq <= 0:
            # When scoping to agent operations, pre-filter the SQL read to the
            # operation types: without it, high-frequency non-operation rows
            # (user.activity page reports) evict real operations from the
            # newest-limit window. The backfill loop then keeps walking
            # backward while the in-memory attribution filter starves the
            # window (bounded: 6 rounds x cap rows scanned).
            sql_types = type_list
            if agent and sql_types is None:
                sql_types = tuple(sorted(_OPERATION_TYPES))
            before = bus.log.latest_seq() + 1
            kept: list[tuple[int, Event]] = []
            for _round in range(6):
                chunk = bus.log.read_before(before_seq=before, types=sql_types, limit=cap)
                if not chunk:
                    break
                before = chunk[0][0]
                kept[:0] = [pair for pair in chunk if _wanted(pair[1])]
                if len(kept) >= cap:
                    break
            rows = kept[-cap:]
        else:
            rows = bus.log.read_after(after_seq=after_seq, types=type_list, limit=cap)

        return {"events": [{"seq": seq, **e.to_dict()} for seq, e in rows if _wanted(e)]}

    return router
