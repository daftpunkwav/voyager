"""Chat channel: publishes user.message, streams events back over SSE.

Responsibilities:
- POST /api/chat/messages: validate and publish user.message (optional
  `session` field targets one chat session; absent -> the user's active
  session, resolved agent-side)
- GET /api/chat/messages: history pages from the event log (newest window
  by default; before_seq pages backward, after_seq pages forward; optional
  `session` filter over the event payload)
- GET /api/chat/trajectory: step rows (agent.step) for rebuilding the
  execution trajectory after a refresh; same paging cursors as history
- GET /api/chat/stream: SSE delivery with after_seq resume (optional
  `session` filter)

Session architecture: the gateway still stores zero business data - a
session is a payload field on the event (agent.message / agent.step /
agent.delta / user.message all carry `session`), and the agent resolves the
active/default session. Rows without a session field predate multi-session
and belong to the global lane; a `session` filter matches only rows stamped
with that exact id. Filtered pages scan backward/forward in chunks so
has_more and the cursors stay correct.

Trajectory rebuild contract: step rows arrive ordered by seq; a step belongs
to the turn whose closing agent.message is the first message row after it.
Live steps still arrive over SSE; this endpoint only backfills.
Newest-window only: the UI consumes the latest window (default 500) and
does not page backward; before_seq/after_seq exist for diagnostics and
tooling, not for the current UI.

SSE resume: the client passes after_seq (last seq received); the stream
first replays log entries, then follows live events. If the subscription
falls behind (lagged), missed events are replayed from the log so no
message is lost.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable
from typing import Protocol

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from platform_contracts import (
    LOCAL_USER,
    ActorRef,
    DomainEvent,
    ErrorSuffix,
    Event,
    ServiceError,
)
from platform_eventbus import EventBus, EventLog

from .ratelimit import RateLimiter

_DOMAIN = "gateway"
#: Session ids ride event payloads; the same strict shape the agent store
#: enforces, validated here so a malformed id is a 400 instead of a stranded
#: message the agent cannot route
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
#: Event types relevant to the human timeline (chat + progress + popups +
#: navigation commands + artifact cards + settings hot-reload + L1 permission
#: prompts + streaming deltas; note.edited is excluded — autosave would be
#: high-frequency noise).
#: Types always use the contracts vocabulary constants; "task.*" is a
#: subscription glob pattern, not a concrete type.
_STREAM_TYPES = (
    DomainEvent.AGENT_MESSAGE,
    DomainEvent.AGENT_ASK,
    DomainEvent.AGENT_NAVIGATE,
    "task.*",
    DomainEvent.AGENT_STEP,
    DomainEvent.AGENT_DELTA,
    DomainEvent.AGENT_POLICY_NOTIFY,
    DomainEvent.NOTE_CREATED,
    DomainEvent.SOURCE_ADDED,
    DomainEvent.SOURCE_READY,
    DomainEvent.SOURCE_REMOVED,
    DomainEvent.SETTINGS_CHANGED,
    DomainEvent.NOTES_UI_CHANGED,
    DomainEvent.WORKSPACE_SWITCHED,
)
# note.created rides along so note receipts survive a refresh (the UI
# rebuilds its deliverable cards from the same history page).
_HISTORY_TYPES = (DomainEvent.USER_MESSAGE, DomainEvent.AGENT_MESSAGE, DomainEvent.NOTE_CREATED)
#: Step rows for trajectory rebuilds (execution detail, never the timeline).
_TRAJECTORY_TYPES = (DomainEvent.AGENT_STEP,)
#: Chunk size for session-filtered scans (multiple of any sane page size)
_FILTER_CHUNK = 400


def _in_session(event: Event, session: str) -> bool:
    """Session match: exact id equality over the payload field; rows without
    the field (legacy) belong to the global lane and match no filter — except
    note receipts, which are session-less by nature (the notes domain does
    not know the chat session) and ride along every lane so their cards
    survive a refresh."""
    ev_session = str(event.payload.get("session") or "")
    if event.type == DomainEvent.NOTE_CREATED:
        return not ev_session or ev_session == session
    return ev_session == session


class TrajectoryReader(Protocol):
    """Query projection over agent.step rows (agent.runtime.trajectory); the
    gateway only reads pages, never the projection's writer side."""

    def steps_page(
        self, *, session: str, after_seq: int, before_seq: int | None, limit: int
    ) -> tuple[list[dict], bool]: ...


def build_chat_router(
    bus: EventBus,
    limiter: RateLimiter,
    *,
    history_page_size: int = 200,
    trajectory_page_size: int = 500,
    trajectory: TrajectoryReader | None = None,
) -> APIRouter:
    log: EventLog = bus.log
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

    def _session_or_400(session: str | None) -> str:
        sid = (session or "").strip()
        if sid and not _SESSION_ID_RE.match(sid):
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.INVALID_INPUT,
                "session must match [A-Za-z0-9_-]{1,64}",
            )
        return sid

    def _page(
        read: Callable[..., list],
        types: tuple,
        session: str,
        after_seq: int,
        before_seq: int | None,
        max_rows: int,
    ) -> list:
        """One page under the shared cursor contract, optionally filtered by
        session.

        `read` dispatches on kwarg: callers pass a lambda that routes
        before_seq=... to log.read_before and after_seq=... to log.read_after.
        Unfiltered reads stay the single bounded read they always were. A
        session filter scans the log in chunks (forward from after_seq, or
        backward toward the tail / before_seq) until max_rows+1 matches are
        collected or the log ends, so `has_more` and the trim direction keep
        their original meaning.
        """
        if not session:
            if before_seq is not None:
                rows = read(before_seq=before_seq, types=types, limit=max_rows + 1)
            elif after_seq > 0:
                rows = read(after_seq=after_seq, types=types, limit=max_rows + 1)
            else:
                rows = read(before_seq=log.latest_seq() + 1, types=types, limit=max_rows + 1)
            return rows[-(max_rows + 1) :] if after_seq > 0 else rows

        matched: list[tuple[int, Event]] = []
        if after_seq > 0:  # forward: stop at the first max_rows+1 matches
            cursor = after_seq
            while len(matched) <= max_rows:
                rows = read(after_seq=cursor, types=types, limit=_FILTER_CHUNK)
                if not rows:
                    break
                cursor = rows[-1][0]
                matched.extend((s, e) for s, e in rows if _in_session(e, session))
            return matched[: max_rows + 1]
        # backward: from before_seq (or the tail) toward older rows
        cursor = before_seq if before_seq is not None else log.latest_seq() + 1
        while len(matched) <= max_rows:
            rows = read(before_seq=cursor, types=types, limit=_FILTER_CHUNK)
            if not rows:
                break
            cursor = rows[0][0]
            matched[:0] = [(s, e) for s, e in rows if _in_session(e, session)]
        return matched[-(max_rows + 1) :]

    @router.post("/api/chat/messages")
    async def post_message(request: Request) -> dict:
        body = await _json_body(request)
        content = str(body.get("content") or "").strip()
        if not content:
            raise ServiceError(
                _DOMAIN, ErrorSuffix.INVALID_INPUT, "Message content must not be empty"
            )
        session = _session_or_400(body.get("session"))
        actor = _actor(request)
        limiter.check(actor.id)
        seq = await bus.publish(
            Event(
                type=DomainEvent.USER_MESSAGE,
                actor=actor,
                payload={"content": content, "session": session},
            )
        )
        return {"seq": seq}

    @router.get("/api/chat/messages")
    async def get_messages(
        after_seq: int = 0,
        before_seq: int | None = None,
        limit: int = history_page_size,
        session: str = "",
    ) -> dict:
        """History page with three cursor modes:
        - no cursor: the NEWEST `limit` events (initial UI load must show the
          latest conversation, not the first page ever written);
        - before_seq: the page immediately older than before_seq (backward
          "load earlier" paging, ascending);
        - after_seq > 0: events after after_seq (forward paging, ascending).
        has_more tells whether paging further in the same direction can
        return more rows. `session` narrows the page to one chat session's
        rows (payload filter; the gateway keeps storing zero business data)."""
        sid = _session_or_400(session)
        max_rows = max(1, limit)
        rows = _page(
            lambda **kw: log.read_before(**kw) if "before_seq" in kw else log.read_after(**kw),
            _HISTORY_TYPES,
            sid,
            after_seq,
            before_seq,
            max_rows,
        )
        has_more = len(rows) > max_rows
        if has_more:
            # Over-page trim: backward reads keep the rows nearest the cursor
            # (the tail of the ascending window), forward reads the head
            rows = rows[-max_rows:] if after_seq <= 0 else rows[:max_rows]
        return {
            "has_more": has_more,
            "messages": [{"seq": seq, **e.to_dict()} for seq, e in rows],
        }

    @router.get("/api/chat/trajectory")
    async def get_trajectory(
        after_seq: int = 0,
        before_seq: int | None = None,
        limit: int = trajectory_page_size,
        session: str = "",
    ) -> dict:
        """Step page with the same three cursor modes and session filter as
        history, over agent.step rows only (see the module contract for
        regrouping)."""
        sid = _session_or_400(session)
        max_rows = max(1, limit)
        if trajectory is not None:
            # Projection path: same cursor contract, no log scan
            steps, more = trajectory.steps_page(
                session=sid, after_seq=after_seq, before_seq=before_seq, limit=max_rows
            )
            return {"has_more": more, "steps": steps}
        rows = _page(
            lambda **kw: log.read_before(**kw) if "before_seq" in kw else log.read_after(**kw),
            _TRAJECTORY_TYPES,
            sid,
            after_seq,
            before_seq,
            max_rows,
        )
        has_more = len(rows) > max_rows
        if has_more:
            rows = rows[-max_rows:] if after_seq <= 0 else rows[:max_rows]
        return {
            "has_more": has_more,
            "steps": [{"seq": seq, **e.to_dict()} for seq, e in rows],
        }

    @router.get("/api/chat/stream")
    async def stream(
        request: Request, after_seq: int = -1, once: bool = False, session: str = ""
    ) -> StreamingResponse:
        """once=true: replay backlog after after_seq, then close (no long-lived stream).
        `session` filters frames to one chat session (empty = all frames)."""
        sid = _session_or_400(session)
        actor = _actor(request)
        limiter.check(actor.id)
        limiter.acquire_sse()
        # No explicit after_seq -> start from the current tail (history is
        # served by GET /api/chat/messages, not replayed here)
        start_seq = log.latest_seq() if after_seq < 0 else after_seq

        def _wanted(event: Event) -> bool:
            return not sid or _in_session(event, sid)

        async def gen() -> AsyncIterator[str]:
            cursor = start_seq
            sub = bus.subscribe(*_STREAM_TYPES)
            try:
                for seq, event in log.read_after(after_seq=cursor, types=_STREAM_TYPES):
                    cursor = max(cursor, seq)
                    if _wanted(event):
                        yield _frame(event, seq)
                if once:
                    return
                while not await request.is_disconnected():
                    if sub.lagged:  # fell behind: replay missing events from the log
                        for seq, event in log.read_after(after_seq=cursor, types=_STREAM_TYPES):
                            cursor = max(cursor, seq)
                            if _wanted(event):
                                yield _frame(event, seq)
                        sub.lagged = False
                    try:
                        event = await sub.get(timeout=15.0)
                    except TimeoutError:
                        yield ": ping\n\n"  # keep-alive heartbeat
                        continue
                    cursor = max(cursor, sub.last_seq)
                    if _wanted(event):
                        yield _frame(event, cursor)
            finally:
                bus.unsubscribe(sub)
                limiter.release_sse()

        return StreamingResponse(gen(), media_type="text/event-stream")

    return router


def _frame(event: Event, seq: int) -> str:
    return f"id: {seq}\ndata: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"
