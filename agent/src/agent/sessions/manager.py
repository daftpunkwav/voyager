"""Session manager: one conversational instance per chat session,
lazily restored from the store, with per-session locks.

Design notes:
- The manager owns session identity and lifecycle (create / fork / rename /
  delete / active pointer / persistence). Master owns the message flow;
  capabilities and the session meta tools share this one manager, so the
  human path and the agent path drive the same engine.
- Instances are cached and lazily restored: listings read store metadata
  only, and a session's instance (with its history) is rebuilt on first use
  after a restart. Store-less wiring (older tests) degrades to in-memory
  sessions with generated ids and no persistence.
- Deleting a running session is refused; switching and deleting stay on the
  human side by design - an agent switching the session the user is looking
  at would break the conversational contract (fork+create cover the agent's
  autonomy needs).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from platform_capability import current_chat_session
from platform_contracts import (
    ActorKind,
    ActorRef,
    DomainEvent,
    ErrorSuffix,
    Event,
    ServiceError,
)
from platform_eventbus import EventBus

from agent.engine import Mode, Spawner, SubagentInstance, TaskBook
from agent.prompts import P
from agent.runtime.state import RunStatus
from agent.sessions.store import (
    SessionSnapshot,
    SessionStore,
    is_valid_session_id,
)

log = logging.getLogger("agent.sessions")

#: Emitter identity for session lifecycle events (the manager itself is the
#: source; whether a *human* or the *agent* drove the delete is carried by
#: the payload's session field, not the actor).
_SESSIONS_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="agent.sessions")

# The standing goal of the conversational instance (prompt data lives in
# prompts/definitions/orchestrator.toml).
CHAT_GOAL = P.orchestrator.chat_goal

#: Sessions shown with this label until the first user message seeds a title
UNTITLED_LABEL = "新会话"

#: Cap on resident sessions; deletes stay user-driven, so only a soft guard
MAX_SESSIONS = 200


def new_session_id() -> str:
    return uuid.uuid4().hex[:8]


class SessionManager:
    """Session registry + conversational instance cache."""

    def __init__(
        self,
        *,
        spawner: Spawner,
        sink_fn: Callable[[str], Callable[[str], Awaitable[None]]],
        store: SessionStore | None = None,
        chat_goal: str = CHAT_GOAL,
        bus: EventBus | None = None,
        on_delete: Callable[[str], None] | None = None,
    ) -> None:
        self._spawner = spawner
        self._sink_fn = sink_fn  # session_id -> reply sink for that session
        self._bus = bus
        # Called with the deleted session id after in-memory teardown: the
        # Master drops that session's queued-message inbox, so messages parked
        # mid-turn cannot re-attach when the same id is recreated later.
        self._on_delete = on_delete
        # session_id -> raw round recorder factory; attached post-construction
        # by the assembler (the trajectory store does not exist yet earlier).
        self._raw_fn: Callable[[str], Callable[[str, int, list, Any], Awaitable[None]]] | None = (
            None
        )
        self._store = store
        self._chat_goal = chat_goal
        self._instances: dict[str, SubagentInstance] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        # Store-less mode still needs an active pointer and title tracking
        self._active: str = ""
        self._titles: dict[str, str] = {}

    def set_raw_fn(
        self, fn: Callable[[str], Callable[[str, int, list, Any], Awaitable[None]]]
    ) -> None:
        """Attach the per-session raw round recorder factory (assembly-time;
        instances spawned before this call simply log nothing)."""
        self._raw_fn = fn

    # -- resolution & instances ---------------------------------------------

    def resolve(self, session_id: str = "", *, seed_title: str = "") -> SubagentInstance:
        """Resolve a session id (or the active one) to its instance. Unknown
        ids raise NOT_FOUND when a store is wired (creation is the caller's
        fallback — see master.handle_user_message); store-less wiring spawns
        instances on demand. The first user message seeds the title of an
        untitled session."""
        sid = self._normalize_target(session_id)
        inst = self._instances.get(sid)
        if inst is None:
            snap = self._store.get(sid) if self._store is not None else None
            if snap is None:
                if self._store is not None:
                    raise ServiceError(
                        "agent",
                        ErrorSuffix.NOT_FOUND,
                        f"session not found: {sid}",
                        hint="session(action=list) first or pass no session id",
                    )
                # Store-less mode: instances are created on demand
                inst = self._spawn_instance(sid, None)
            else:
                inst = self._spawn_instance(sid, snap)
            self._instances[sid] = inst
        if seed_title and not self._title_of(sid):
            self.rename(sid, seed_title[:24])
        return inst

    def _normalize_target(self, session_id: str) -> str:
        """Empty target -> active session (creating the default one on a
        fresh store so legacy single-conversation callers keep working)."""
        sid = (session_id or "").strip()
        if sid:
            return sid
        sid = self.active_id()
        if sid:
            return sid
        return self._default_session()

    def _default_session(self) -> str:
        """The first session of a fresh deployment: id 'chat' (legacy-friendly)
        when the store is empty, else the most recently updated one."""
        if self._store is None:
            sid = new_session_id()
            self._titles[sid] = ""
            self._active = sid
            return sid
        sessions = self._store.list()
        if not sessions:
            self._store.create("chat", title="")
            self._store.set_active("chat")
            return "chat"
        sid = sessions[0].session_id
        self._store.set_active(sid)
        return sid

    def _spawn_instance(
        self,
        session_id: str,
        snap: Any,  # SessionSnapshot | None
    ) -> SubagentInstance:
        persona = (snap.persona if snap is not None else "") or "orchestrator"
        goal = (snap.goal if snap is not None else "") or self._chat_goal
        inst = self._spawner.spawn(
            TaskBook(goal=goal, mode=Mode.REACT, conversational=True, session=session_id),
            persona=persona,
            name="chat",
            reply_sink=self._sink_fn(session_id),
            raw_recorder=self._raw_fn(session_id) if self._raw_fn is not None else None,
        )
        if snap is not None:
            inst.history = [dict(m) for m in snap.history]
            if snap.active_tools:
                inst.active = set(snap.active_tools)
        return inst

    def target_id(self, session_id: str = "") -> str:
        """Public target resolution: an explicit id, else the active session
        (creating the default one on a fresh store)."""
        return self._normalize_target(session_id)

    def snapshot(self, session_id: str) -> Any:
        """Persisted snapshot of one session; None when unknown or store-less."""
        return self._store.get(session_id) if self._store is not None else None

    def instance_for(self, session_id: str) -> SubagentInstance | None:
        """Cached instance for an existing session; None when unknown."""
        inst = self._instances.get(session_id)
        if inst is not None:
            return inst
        if self._store is None:
            return self._instances.get(session_id)
        if self._store.get(session_id) is None:
            return None
        inst = self._spawn_instance(session_id, self._store.get(session_id))
        self._instances[session_id] = inst
        return inst

    # -- lifecycle ------------------------------------------------------------

    def create(
        self, title: str = "", persona: str = "orchestrator", session_id: str = ""
    ) -> dict[str, Any]:
        """Create a fresh empty session (does not switch the active one)."""
        if session_id and not is_valid_session_id(session_id):
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"会话 ID 不合法: {session_id!r}(仅限字母/数字/下划线/连字符,≤64 字符)",
                hint="omit session_id to generate one, or match [A-Za-z0-9_-]{1,64}",
            )
        if self._store is not None and len(self._store.list()) >= MAX_SESSIONS:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"session count reached the cap ({MAX_SESSIONS}); delete some first",
            )
        sid = session_id or new_session_id()
        if self._store is not None:
            if self._store.get(sid) is not None:
                raise ServiceError("agent", ErrorSuffix.CONFLICT, f"session already exists: {sid}")
            self._store.create(sid, title=title, persona=persona)
        else:
            self._titles[sid] = title
        return {"session_id": sid, "title": title, "persona": persona}

    def fork(
        self, source_session_id: str = "", title: str = "", keep_messages: int = 0
    ) -> dict[str, Any]:
        """New session seeded with a copy of the source session's history
        (default source: the active session)."""
        source = self.instance_for(self._normalize_target(source_session_id))
        if source is None:
            raise ServiceError(
                "agent",
                ErrorSuffix.NOT_FOUND,
                f"session not found: {source_session_id or '(active)'}",
            )
        created = self.create(title=title or self._title_of(source.session) + " 分支")
        sid = created["session_id"]
        inst = self._spawn_instance(sid, None)
        history = [dict(m) for m in source.history]
        if keep_messages > 0:
            # Message-level fork: only the first N entries (user/assistant
            # pairs), so the branch resumes from a chosen point in time.
            history = history[:keep_messages]
        inst.history = history
        if source.active:
            inst.active = set(source.active)
        self._instances[sid] = inst
        self.persist(sid)
        self._persist_fork_parent(sid, source.session)
        return {**created, "forked_from": source.session}

    def set_flags(
        self, session_id: str, *, pinned: bool | None = None, archived: bool | None = None
    ) -> dict[str, Any]:
        """User curation flags on the persisted snapshot (pinned/archived)."""
        sid = self._normalize_target(session_id)
        snap = (
            self._store.set_flags(sid, pinned=pinned, archived=archived)
            if self._store is not None
            else None
        )
        if snap is None:
            raise ServiceError(
                "agent",
                ErrorSuffix.NOT_FOUND,
                f"session not found: {sid or '(active)'}",
            )
        return {"session_id": sid, "pinned": snap.pinned, "archived": snap.archived}

    def rename(self, session_id: str, title: str) -> None:
        """Rename an existing session; unknown ids raise instead of silently
        reporting success (a rename that renames nothing is a client bug)."""
        sid = self._normalize_target(session_id)
        title = title.strip()
        known = (
            self._store.get(sid) is not None
            if self._store is not None
            else sid in self._titles or sid in self._instances
        )
        if not known:
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND, f"session not found: {sid}")
        if self._store is not None:
            self._store.rename(sid, title)
        else:
            self._titles[sid] = title

    def delete(self, session_id: str) -> dict[str, Any]:
        """Delete a session; refused while its instance is mid-turn."""
        sid = self._normalize_target(session_id)
        inst = self._instances.get(sid)
        if inst is not None and inst.status is RunStatus.RUNNING:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"session {sid} is running; cancel the turn before deleting",
            )
        title = self._title_of(sid)
        self._instances.pop(sid, None)
        self._locks.pop(sid, None)
        if self._on_delete is not None:
            self._on_delete(sid)
        if self._store is not None:
            if self._store.get(sid) is None:
                raise ServiceError("agent", ErrorSuffix.NOT_FOUND, f"session not found: {sid}")
            self._store.delete(sid)
        else:
            self._titles.pop(sid, None)
        if self.active_id() == sid:
            nxt = (
                self._store.list()[0].session_id
                if self._store is not None and self._store.list()
                else ""
            )
            self._active = nxt
            if self._store is not None:
                if nxt:
                    self._store.set_active(nxt)
                else:
                    self._store.set_active("")
        self._emit_session_deleted(sid, title)
        return {"deleted": sid}

    def _emit_session_deleted(self, sid: str, title: str) -> None:
        """Land a session.deleted row in the shared event log. Sync append:
        this runs inside the sync capability dispatch, possibly on a worker
        thread, so live SSE subscribers are not pushed - the activity page
        reads the log and is the consumer. The session field marks
        agent-initiated deletes (the invocation context is set inside a chat
        turn); human deletes stay session-less, which is how the two are
        told apart downstream."""
        if self._bus is None:
            return
        payload: dict[str, Any] = {"deleted": sid, "title": title}
        session = current_chat_session.get()
        if session:
            payload["session"] = session
        self._bus.log.append(
            Event(type=DomainEvent.SESSION_DELETED, actor=_SESSIONS_ACTOR, payload=payload)
        )

    def set_active(self, session_id: str) -> dict[str, Any]:
        sid = (session_id or "").strip()
        known = (
            self._store.get(sid) is not None
            if self._store is not None
            else sid in self._titles or sid in self._instances
        )
        if not known:
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND, f"session not found: {sid}")
        self._active = sid
        if self._store is not None:
            self._store.set_active(sid)
        return {"active": sid}

    # -- queries & plumbing -----------------------------------------------------

    def active_id(self) -> str:
        if self._active:
            return self._active
        if self._store is not None:
            self._active = self._store.get_active()
        return self._active

    def _persist_fork_parent(self, sid: str, parent: str) -> None:
        """Record fork lineage in the store's meta table (best effort: lineage
        is search convenience, not conversation state)."""
        if self._store is None:
            return
        try:
            self._store.set_meta(f"fork_parent:{sid}", parent)
        except Exception:  # lineage must not break forking
            log.warning("persisting fork lineage failed", exc_info=True)

    def lineage(self, session_id: str) -> dict[str, Any]:
        """Fork lineage for one session: ancestors up the parent chain plus
        the direct children (sessions forked from it)."""
        sid = self._normalize_target(session_id)
        if self.instance_for(sid) is None:
            raise ServiceError(
                "agent", ErrorSuffix.NOT_FOUND, f"session not found: {session_id or '(active)'}"
            )
        ancestors: list[str] = []
        cur = sid
        seen: set[str] = {sid}
        while self._store is not None:
            parent = self._store.get_meta(f"fork_parent:{cur}")
            if not parent or parent in seen:
                break
            ancestors.append(parent)
            seen.add(parent)
            cur = parent
        children = (
            [k.removeprefix("fork_parent:") for k in self._store.meta_by_value("fork_parent:", sid)]
            if self._store is not None
            else []
        )
        return {"session": sid, "ancestors": ancestors, "children": children}

    def _title_of(self, session_id: str) -> str:
        if self._store is not None:
            snap = self._store.get(session_id)
            return snap.title if snap is not None else ""
        return self._titles.get(session_id, "")

    def list(self) -> list[dict[str, Any]]:
        """Listing rows (metadata + live status), most recent first."""
        rows: list[dict[str, Any]] = []
        active = self.active_id()
        if self._store is not None:
            for meta in self._store.list():
                inst = self._instances.get(meta.session_id)
                rows.append(
                    {
                        "session_id": meta.session_id,
                        "title": meta.title or UNTITLED_LABEL,
                        "persona": meta.persona,
                        "created_at": meta.created_at,
                        "updated_at": meta.updated_at,
                        "active": meta.session_id == active,
                        "status": inst.status.value if inst is not None else "stored",
                        "turns": (len(inst.history) // 2) if inst is not None else None,
                        "pinned": meta.pinned,
                        "archived": meta.archived,
                    }
                )
        else:
            for sid, inst in self._instances.items():
                rows.append(
                    {
                        "session_id": sid,
                        "title": self._titles.get(sid) or UNTITLED_LABEL,
                        "persona": inst.persona,
                        "created_at": None,
                        "updated_at": None,
                        "active": sid == active,
                        "status": inst.status.value,
                        "turns": len(inst.history) // 2,
                    }
                )
        return rows

    def lock_for(self, session_id: str) -> asyncio.Lock:
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock
        return lock

    def persist(self, session_id: str) -> None:
        """Best-effort persistence of one session's instance after a turn; a
        failure logs and moves on - losing one snapshot never blocks chatting."""
        if self._store is None:
            return
        inst = self._instances.get(session_id)
        if inst is None or not inst.task.conversational:
            return
        try:
            snap = self._store.get(session_id)
            self._store.save(
                SessionSnapshot(
                    session_id=session_id,
                    title=(snap.title if snap is not None else "") or self._title_of(session_id),
                    persona=inst.persona,
                    goal=inst.task.goal,
                    history=[dict(m) for m in inst.history],
                    active_tools=sorted(inst.active) if inst.active else [],
                    created_at=snap.created_at if snap is not None else 0.0,
                    # Curation flags must survive turn persistence, or a pin
                    # would be silently dropped by the next chat message.
                    pinned=snap.pinned if snap is not None else False,
                    archived=snap.archived if snap is not None else False,
                )
            )
        except Exception:
            log.warning("session persistence failed: %s", session_id, exc_info=True)


__all__ = ["CHAT_GOAL", "UNTITLED_LABEL", "SessionManager", "new_session_id"]
