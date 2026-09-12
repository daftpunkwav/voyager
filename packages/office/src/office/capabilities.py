"""Aggregate registry for the office service: merges the doc/slides
sub-registries, no logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from platform_capability import Registry
from platform_eventbus import EventBus

from .modules.doc import capabilities as doc_caps
from .modules.doc.capabilities import DocDeps
from .modules.slides import capabilities as slides_caps
from .modules.slides.capabilities import SlidesDeps
from .store import DocumentStore

registry = Registry("office")
registry.merge(doc_caps.registry, slides_caps.registry)


@dataclass
class OfficeDeps:
    """Sub-module dependencies assembled by the aggregate layer."""

    store: DocumentStore
    bus: EventBus | None


def init_all(deps: OfficeDeps) -> None:
    doc_caps.init_deps(DocDeps(store=deps.store, bus=deps.bus))
    slides_caps.init_deps(SlidesDeps(store=deps.store, bus=deps.bus))
