"""Sub-module registry for slides (PowerPoint-like) capabilities.

Responsibilities:
- CRUD capabilities for slide decks (create/get/update/delete), restricted
  to kind='slides' rows of the shared store
- Slide-level editing (add_slide) and doc.created/edited/deleted events
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from platform_capability import Registry, capability
from platform_contracts import ActorKind, ActorRef, DomainEvent, ErrorSuffix, Event, ServiceError
from platform_eventbus import EventBus

from ...store import DocumentStore

_DOMAIN = "office"
_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="office.slides")
registry = Registry("office.slides")


@dataclass
class SlidesDeps:
    store: DocumentStore
    bus: EventBus | None


_deps: SlidesDeps | None = None


def init_deps(deps: SlidesDeps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> SlidesDeps:
    if _deps is None:
        raise RuntimeError("deps not injected")
    return _deps


def _require_deck(did: str) -> dict[str, Any]:
    deck = _require_deps().store.get(did)
    if deck is None or deck["kind"] != "slides":
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"Deck not found: {did}")
    return deck


async def _emit(type_: str, did: str, **payload) -> None:
    deps = _require_deps()
    if deps.bus is not None:
        await deps.bus.publish(Event(type=type_, actor=_ACTOR, payload={"deck_id": did, **payload}))


@capability(registry, name="create_deck", description="Create a PPT-like deck")
async def create_deck(title: str, slides: list[dict] | None = None) -> dict[str, Any]:
    deps = _require_deps()
    deck = deps.store.create(title, "slides", slides)
    await _emit(DomainEvent.DOC_CREATED, deck["id"], title=title)
    return deck


@capability(registry, name="get_deck", description="Read all slides of a deck")
def get_deck(deck_id: str) -> dict[str, Any]:
    return _require_deck(deck_id)


@capability(registry, name="update_deck", description="Replace all slides")
async def update_deck(deck_id: str, slides: list[dict]) -> dict[str, Any]:
    deps = _require_deps()
    _require_deck(deck_id)
    deck = deps.store.update(deck_id, blocks=slides)
    await _emit(DomainEvent.DOC_EDITED, deck_id)
    return deck


@capability(registry, name="add_slide", description="Append a slide at the end")
async def add_slide(deck_id: str, slide: dict) -> dict[str, Any]:
    deps = _require_deps()
    deck = _require_deck(deck_id)
    slides: list[dict] = deck["blocks"]
    slides.append(slide)
    deck = deps.store.update(deck_id, blocks=slides)
    await _emit(DomainEvent.DOC_EDITED, deck_id)
    return deck


@capability(registry, name="delete_deck", description="Delete a deck", reversible=False)
async def delete_deck(deck_id: str) -> dict[str, Any]:
    deps = _require_deps()
    deck = _require_deck(deck_id)
    deps.store.delete(deck_id)
    await _emit(DomainEvent.DOC_DELETED, deck_id, title=deck["title"])
    return {"deleted": deck_id, "title": deck["title"]}


__all__ = ["SlidesDeps", "init_deps", "registry"]
