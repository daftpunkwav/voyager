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
from platform_contracts import LOCAL_USER, ActorRef, DomainEvent, ErrorSuffix, Event, ServiceError
from platform_eventbus import EventBus

from .ratelimit import RateLimiter

_DOMAIN = "gateway"
_ACTIVITY_KINDS = ("page_view", "pointer", "selection", "manual")  # initial kinds


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
        events attributed to a chat turn (payload.session stamped by the
        capability invocation context); `session=<id>` keeps only one
        session's events (implies agent). The type filter still narrows the
        SQL read; agent/session filter in memory afterwards, so a heavily
        filtered page may return fewer rows than `limit`."""
        type_list = tuple(t for t in types.split(",") if t) or None
        cap = max(1, min(limit, 1000))
        if recent and after_seq <= 0:
            rows = bus.log.read_before(
                before_seq=bus.log.latest_seq() + 1, types=type_list, limit=cap
            )
            rows.reverse()  # keep the feed's oldest-first row order
        else:
            rows = bus.log.read_after(after_seq=after_seq, types=type_list, limit=cap)

        def _wanted(ev: Event) -> bool:
            ev_session = str(ev.payload.get("session") or "")
            if session:
                return ev_session == session
            if agent:
                return bool(ev_session)
            return True

        return {"events": [{"seq": seq, **e.to_dict()} for seq, e in rows if _wanted(e)]}

    return router
