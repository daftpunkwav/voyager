"""Aggregated sources registry: merges submodule registries and serves the
unified cross-kind resource stream.

Submodules under modules/ are self-contained and never import each other;
this shell only merges them read-only. The unified stream (list_sources /
search_sources / sources_stats) does pure fan-out plus merged sorting:
every submodule store exposes summaries()/stats() of the same shape, so
the aggregation layer has no kind-specific branching. Adding a resource
kind means one STORES registration and zero aggregate changes.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError
from platform_eventbus import EventBus
from platform_secrets import SecretStore
from platform_settings import SettingsStore

from .modules.doc import capabilities as doc_caps
from .modules.doc.store import DocStore
from .modules.repo import capabilities as repo_caps
from .modules.repo.store import RepoStore
from .modules.web import capabilities as web_caps
from .modules.web.store import WebStore

_DOMAIN = "sources"

registry = Registry(_DOMAIN)
registry.merge(repo_caps.registry, doc_caps.registry, web_caps.registry)

#: kind -> store; populated by wiring (init_all), read for aggregate fan-out
STORES: dict[str, RepoStore | DocStore | WebStore] = {}


@dataclass
class SourcesDeps:
    """Submodule dependencies assembled by the aggregation layer."""

    repo_store: RepoStore
    doc_store: DocStore
    web_store: WebStore
    secrets: SecretStore
    bus: EventBus | None
    repo_queue: asyncio.Queue
    doc_queue: asyncio.Queue
    workspace: Path
    settings: SettingsStore | None = None  # doc submodule reads the parse cap


def init_all(deps: SourcesDeps) -> None:
    repo_caps.init_deps(
        repo_caps.RepoDeps(
            store=deps.repo_store,
            secrets=deps.secrets,
            bus=deps.bus,
            queue=deps.repo_queue,
            workspace=deps.workspace,
        )
    )
    doc_caps.init_deps(
        doc_caps.DocDeps(
            store=deps.doc_store,
            bus=deps.bus,
            queue=deps.doc_queue,
            workspace=deps.workspace,
            settings=deps.settings,
        )
    )
    web_caps.init_deps(web_caps.WebDeps(store=deps.web_store, bus=deps.bus))
    STORES.clear()
    STORES.update({"repo": deps.repo_store, "doc": deps.doc_store, "web": deps.web_store})


def _stores(kind: str) -> list:
    """Stores for a kind; an unknown kind raises INVALID_INPUT (argument validation)."""
    kind = kind.strip().lower()
    if kind and kind not in STORES:
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            f"Unknown resource kind: {kind}",
            hint=f"One of: {'/'.join(sorted(STORES))}, or leave empty for all",
        )
    if kind:
        return [STORES[kind]]
    return [STORES[k] for k in sorted(STORES)]


_SORT_KEYS = {"added": "added_ts", "updated": "updated_ts", "title": "title"}

#: Per-store fan-out row cap; must stay >= the graph L0 per-kind fetch
#: (2000), otherwise L0 (host resource catalog bridge) is silently
#: truncated into a partial graph
_MAX_PER_STORE = 2000


@capability(
    registry,
    name="list_sources",
    description="List library resource summaries across kinds (unified stream; empty kind=all)",
)
def list_sources(
    kind: str = "",
    status: str = "",
    tag: str = "",
    query: str = "",
    sort: str = "added",
    desc: bool = True,
    limit: int = 200,
) -> list[dict]:
    merged: list[dict] = []
    for store in _stores(kind):
        merged.extend(
            store.summaries(
                status=status.strip(),
                tag=tag.strip(),
                query=query.strip(),
                limit=min(limit, _MAX_PER_STORE),
            )
        )
    key = _SORT_KEYS.get(sort, "added_ts")
    merged.sort(key=lambda r: str(r.get(key) or ""), reverse=desc)
    return merged[:limit]


@capability(
    registry,
    name="search_sources",
    description="Search resources across kinds: title/tag hits + document section-text hits (with section-number locator)",
)
def search_sources(query: str, kind: str = "", limit: int = 20) -> list[dict]:
    query = query.strip()
    if not query:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "query cannot be empty")
    merged: list[dict] = []
    for store in _stores(kind):
        merged.extend(store.summaries(query=query, limit=min(limit, 100)))
    # Doc section-text hits: appended with a section_no locator, deduped
    # against title hits
    if not kind or kind.strip().lower() == "doc":
        doc_store = STORES.get("doc")
        if isinstance(doc_store, DocStore):
            seen = {r["id"] for r in merged}
            for hit in doc_store.search_summaries(query, min(limit, 100)):
                if hit["id"] in seen:
                    continue
                merged.append(hit)
                seen.add(hit["id"])
    merged.sort(key=lambda r: float(r.get("added_ts") or 0.0), reverse=True)
    return merged[:limit]


@capability(
    registry,
    name="sources_stats",
    description="Library statistics (counts per kind plus importing/failed; for agent context summaries)",
)
def sources_stats() -> dict:
    stats = {name: store.stats() for name, store in STORES.items()}
    out = {name: s["total"] for name, s in stats.items()}
    out["importing"] = sum(s.get("importing", 0) for s in stats.values())
    out["failed"] = sum(s.get("failed", 0) for s in stats.values())
    return out
