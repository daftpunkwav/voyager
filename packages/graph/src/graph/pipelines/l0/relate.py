"""L0 pipeline, cross-resource relations: resource-library metadata
-> the "universe" namespace relation graph.

Layering: L0 = cross-resource relation layer (this module); L1 = deep
single-resource analysis (code repos via the engines, other kinds via AI
pipeline agents).

The resource inventory comes from the late-bound call ``call(domain, name,
args)`` injected by wiring (shape aligned with the sources list_sources
summary) -- graph never imports sources; the dependency is inverted to the
composition root, and the call rides the same capability guard chain as UI
and agent traffic. The current rule is deterministic tag-overlap fallback
(source="meta"); AI semantic relations are additive
(set_node/set_relationship, source="ai") and survive rebuilds.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from typing import Any

from ...store import GraphStore

#: Project namespace of the L0 relation graph
L0_PROJECT = "universe"

#: Resource kinds participating in relations (aligned with sources list_sources)
L0_KINDS = ("repo", "doc", "web")

#: Resources that are not ready / failed do not participate in relations
_EXCLUDED_STATUS = {"failed", "importing", "parsing"}

#: Per-run resource cap (guards against O(n^2) pairwise comparison)
MAX_RESOURCES = 1000

#: Per-kind inventory fetch cap (passed through to the provider call)
LIST_LIMIT = 2000

#: Late-bound cross-domain call: (domain, name, args) -> result dict.
#: Synchronous twin only: L0 runs on a worker thread via asyncio.to_thread.
SyncCall = Callable[[str, str, dict], Any]


def run_l0(store: GraphStore, call_sync: SyncCall | None, *, kinds: list[str]) -> dict[str, Any]:
    """Rebuild the meta relation graph in the universe namespace; returns stats.

    Idempotent: first purge stale meta edges and resource nodes that have
    disappeared (keeping AI output), then fully rewrite nodes and
    tag-overlap edges from the current resource snapshot.
    """
    if call_sync is None:
        raise RuntimeError(
            "L0 relation analysis requires the resource catalog: run in the "
            "aggregate shape (host injects call_sync), or import resources "
            "into the resource library first"
        )
    unknown = [k for k in kinds if k not in L0_KINDS]
    if unknown:
        raise ValueError(f"unknown resource kinds: {unknown} (allowed: {list(L0_KINDS)})")
    if not kinds:
        raise ValueError(
            "kinds must not be empty: select at least one resource kind for relation analysis"
        )

    raw: list[dict[str, Any]] = []
    for kind in kinds:
        rows = call_sync("sources", "list_sources", {"kind": kind, "limit": LIST_LIMIT})
        raw.extend(rows if isinstance(rows, list) else [])
    resources = [r for r in raw if str(r.get("status", "ready")) not in _EXCLUDED_STATUS]
    truncated = len(resources) > MAX_RESOURCES
    if truncated:
        # Truncate deterministically: sort by (kind, id) and keep the first MAX_RESOURCES
        resources.sort(key=lambda r: (str(r.get("kind")), str(r.get("id"))))
        resources = resources[:MAX_RESOURCES]

    purged = store.purge_meta(L0_PROJECT, keep_qn={_qn(r) for r in resources})

    nodes = 0
    node_ids: dict[str, str] = {}
    for r in resources:
        row = store.upsert_node(
            L0_PROJECT,
            "Resource",
            str(r.get("title") or r.get("id")),
            _qn(r),
            {
                "kind": str(r.get("kind")),
                "tags": list(r.get("tags") or []),
                "category": str(r.get("category") or ""),
                "status": str(r.get("status", "ready")),
                "subtitle": str(r.get("subtitle") or ""),
            },
            source="meta",
            actor="pipeline.l0",
        )
        node_ids[_qn(r)] = row["id"]
        nodes += 1

    edges = 0
    by_tags = [(r, {t for t in (r.get("tags") or []) if t}) for r in resources]
    for (ra, ta), (rb, tb) in itertools.combinations(by_tags, 2):
        shared = sorted(ta & tb)
        if not shared:
            continue
        store.upsert_edge(
            L0_PROJECT,
            node_ids[_qn(ra)],
            node_ids[_qn(rb)],
            "RELATED",
            {"shared_tags": shared},
            source="meta",
            actor="pipeline.l0",
        )
        edges += 1

    return {
        "project": L0_PROJECT,
        "kinds": list(kinds),
        "resources": len(resources),
        "nodes": nodes,
        "related_edges": edges,
        "purged_nodes": purged["nodes"],
        "purged_edges": purged["edges"],
        "truncated": truncated,
    }


def l0_view(
    store: GraphStore, *, kinds: list[str] | None = None, limit: int = 500
) -> dict[str, Any]:
    """Read the L0 view: universe nodes/edges (optionally filtered by kind) plus cross-repo edges.

    CROSS_REPO edges natively live in the cross-repo space (endpoints are the
    L1-indexed Project nodes, qualified_name = project id); here their
    endpoints are resolved to universe repo resource nodes ("repo:{id}") and
    unresolvable edges are dropped, so the view never shows dangling endpoints.
    """
    want = {k for k in (kinds or []) if k}
    graph = store.query(L0_PROJECT, limit=limit)
    if want:
        nodes = [n for n in graph["nodes"] if str(n["attrs"].get("kind")) in want]
    else:
        nodes = graph["nodes"]
    ids = {n["id"] for n in nodes}
    edges = [e for e in graph["edges"] if e["src"] in ids and e["dst"] in ids]

    # cross-repo Project nodes: qualified_name = project id (the project of the
    # L1 enqueue); universe repo resource nodes have qn = "repo:{id}". Both
    # derive from the same id, so the mapping is a direct string join.
    proj_qn = {
        n["id"]: n["qualified_name"]
        for n in store.query("cross-repo", label="Project", limit=10000)["nodes"]
    }
    universe_repo = {
        n["qualified_name"]: n["id"] for n in nodes if str(n["attrs"].get("kind")) == "repo"
    }
    cross: list[dict[str, Any]] = []
    for e in store.cross_edges():
        a = universe_repo.get(f"repo:{proj_qn.get(e['src'], '')}")
        b = universe_repo.get(f"repo:{proj_qn.get(e['dst'], '')}")
        if a in ids and b in ids:
            cross.append({**e, "src": a, "dst": b})
    return {"nodes": nodes, "edges": edges, "cross_edges": cross}


def _qn(r: dict[str, Any]) -> str:
    return f"{r.get('kind')}:{r.get('id')}"
