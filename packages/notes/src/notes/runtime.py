"""Notes service runtime: registry, dependency injection, note
lookup, domain events.

Responsibilities:
- Own the module-level capability registry and the Deps injection point
  (store / bus / settings / asset purge / workspace jail)
- require_alive / get_any: note lookup across live and trashed states
- emit: publish note.* domain events onto the shared bus

Contains no concrete capabilities.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from platform_capability import Registry, current_chat_session
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, Event, ServiceError
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .domain import DOMAIN
from .store import NoteStore

log = logging.getLogger("notes.runtime")

ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="notes.service")
registry = Registry(DOMAIN)

SORT_COL = {"updated": "updated_ts", "created": "created_ts", "title": "title"}
STATES = ("active", "archived", "trash", "all")


@dataclass
class Deps:
    store: NoteStore
    bus: EventBus | None
    settings: SettingsStore | None = None
    purge_assets: Callable[[str], list[str]] | None = None  # also purges attachments on purge
    workspace: Path | None = None  # jail root for import/export; required by wire()


_deps: Deps | None = None


def init_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def require_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("deps not injected: call init_deps() at the service entry point first")
    return _deps


def require_alive(nid: str) -> dict:
    """Fetch a note not in the trash (archived notes remain readable and editable)."""
    note = require_deps().store.get(nid)
    if note is None or note["trashed_ts"] is not None:
        raise ServiceError(DOMAIN, ErrorSuffix.NOT_FOUND, f"Note not found: {nid}")
    return note


def get_any(nid: str) -> dict:
    """Fetch any note by id, including trashed ones (get/version/restore paths)."""
    note = require_deps().store.get(nid)
    if note is None:
        raise ServiceError(DOMAIN, ErrorSuffix.NOT_FOUND, f"Note not found: {nid}")
    return note


async def emit(type_: str, note_id: str, **payload) -> None:
    deps = require_deps()
    if deps.bus is not None:
        # Attribute the event to the chat turn that caused it (session-filtered
        # consumers route on this); '' outside a turn = stay session-less.
        session = current_chat_session.get()
        if session:
            payload["session"] = session
        try:
            await deps.bus.publish(
                Event(type=type_, actor=ACTOR, payload={"note_id": note_id, **payload})
            )
        except Exception:
            # The note write already succeeded: a broken event channel (event-log
            # DB error) must not report the whole capability as failed after the
            # fact.
            log.warning("publishing %s event for note %s failed", type_, note_id, exc_info=True)
