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
    async def activity_feed(after_seq: int = 0, types: str = "", limit: int = 200) -> dict:
        type_list = tuple(t for t in types.split(",") if t) or None
        rows = bus.log.read_after(
            after_seq=after_seq, types=type_list, limit=max(1, min(limit, 1000))
        )
        return {"events": [{"seq": seq, **e.to_dict()} for seq, e in rows]}

    return router
