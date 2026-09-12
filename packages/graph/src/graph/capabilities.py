"""Graph capability registry exposing the public tool surface.

Responsibilities:
- Queue operations: enqueue_index / cancel_index / reorder_queue / list_index_jobs;
- Write primitives: set_node / set_relationship (AI pipeline, upsert semantics,
  validated against the graph guide);
- Read operations: query_graph / get_subgraph / graph_stats / engine_info;
- All reads go through the canonical graph store, never directly to engines
  (except the engine_info health probe via the adapter).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from platform_capability import Registry, capability
from platform_contracts import ActorRef, ErrorSuffix, JobRef, ServiceError
from platform_eventbus import EventBus

from .engines.adapter import EngineAdapter
from .index_queue import IndexQueue
from .pipelines.ai import guide as ai_guide
from .pipelines.l0 import relate as l0_relate
from .store import GraphStore

_DOMAIN = "graph"
registry = Registry(_DOMAIN)


@dataclass
class Deps:
    store: GraphStore
    queue: IndexQueue
    adapter: EngineAdapter
    bus: EventBus | None
    #: L0 late-bound call (domain, name, args) for the resource inventory;
    #: wired in by the composition root
    call_sync: l0_relate.SyncCall | None = None
    #: Path jail for indexing; wire() injects workspace. When unset, enqueue
    #: skips path validation (used by unit-test queues).
    workspace: Path | None = None


_deps: Deps | None = None


def init_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("deps not injected: the service entrypoint must call init_deps() first")
    return _deps


def _ensure_node_id(store: GraphStore, project: str, qn: str, *, source: str, actor: str) -> str:
    """Find a node id by qualified_name, creating a placeholder Term node if absent."""
    for row in store.query(project, keyword=qn, limit=5)["nodes"]:
        if row["qualified_name"] == qn:
            return row["id"]
    node = store.upsert_node(
        project, "Term", qn, qn, {"placeholder": True}, source=source, actor=actor
    )
    return node["id"]


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


# ---------- Queue operations ----------


@capability(
    registry,
    name="enqueue_index",
    description="L1 source index enqueue (deep analysis of code repos; "
    "long-running task, progress via task.* events)",
    long_running=True,
    cost=5,
)
def enqueue_index(project: str, repo_path: str, priority: int = 100) -> JobRef:
    deps = _require_deps()
    if deps.workspace is not None and not _within(Path(repo_path), deps.workspace):
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.FORBIDDEN,
            "index path must be inside workspace/",
            hint="place the repo under workspace/repo before enqueueing; "
            "scanning outside the jail is forbidden",
        )
    jid = deps.queue.enqueue(project, repo_path, priority, level="l1")
    return JobRef(job_id=jid)


@capability(
    registry,
    name="enqueue_l0",
    description="L0 cross-resource relation analysis enqueue (kinds "
    "selects a subset of resource kinds; tag overlap is "
    "the deterministic fallback, AI semantic relations "
    "are additive)",
    long_running=True,
    cost=3,
)
def enqueue_l0(kinds: list[str], priority: int = 100) -> JobRef:
    deps = _require_deps()
    unknown = [k for k in kinds if k not in l0_relate.L0_KINDS]
    if unknown:
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            f"unknown resource kinds: {unknown} (allowed: {list(l0_relate.L0_KINDS)})",
        )
    if not kinds:
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            "kinds must not be empty: select at least one resource kind for relation analysis",
        )
    jid = deps.queue.enqueue(
        l0_relate.L0_PROJECT, "", priority, level="l0", kinds=sorted(set(kinds))
    )
    return JobRef(job_id=jid)


@capability(
    registry,
    name="l0_view",
    description="L0 relation graph view (universe-space nodes/edges, "
    "filterable by resource kind; includes cross-repo "
    "relation edges)",
)
def l0_view(kinds: list[str] | None = None, limit: int = 500) -> dict:
    return l0_relate.l0_view(_require_deps().store, kinds=kinds, limit=min(limit, 2000))


@capability(registry, name="cancel_index", description="Cancel a queued index job")
def cancel_index(job_id: str) -> dict:
    deps = _require_deps()
    if not deps.queue.cancel(job_id):
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.CONFLICT,
            "only queued jobs can be cancelled (cooperative "
            "stopping of running jobs is still under development)",
        )
    return {"cancelled": job_id}


@capability(
    registry, name="reorder_queue", description="Reorder the index queue (lower value runs first)"
)
def reorder_queue(job_id: str, priority: int) -> dict:
    deps = _require_deps()
    if not deps.queue.reorder(job_id, priority):
        raise ServiceError(_DOMAIN, ErrorSuffix.CONFLICT, "job is not queued; cannot reorder")
    return {"job_id": job_id, "priority": priority}


@capability(registry, name="list_index_jobs", description="Index queue and job history")
def list_index_jobs(status: str = "") -> list[dict]:
    return _require_deps().queue.list(status)


# ---------- AI pipeline write primitives ----------


@capability(
    registry, name="set_node", description="AI graph building: write/update a node (upsert)", cost=2
)
def set_node(
    project: str,
    label: str,
    name: str,
    qualified_name: str = "",
    attrs: dict | None = None,
    _actor: ActorRef | None = None,
) -> dict:
    ai_guide.validate_node(project, label, name)
    deps = _require_deps()
    actor_id = _actor.id if _actor else ""
    source = "ai" if (_actor and _actor.kind.value == "agent") else "manual"
    return deps.store.upsert_node(
        project, label, name, qualified_name, attrs, source=source, actor=actor_id
    )


@capability(
    registry,
    name="set_relationship",
    description="AI graph building: write/update a relationship; "
    "placeholder nodes are auto-created when either "
    "endpoint is missing",
    cost=2,
)
def set_relationship(
    project: str,
    src: str,
    dst: str,
    type: str,
    attrs: dict | None = None,
    _actor: ActorRef | None = None,
) -> dict:
    ai_guide.validate_relation(project, src, dst, type)
    deps = _require_deps()
    actor_id = _actor.id if _actor else ""
    source = "ai" if (_actor and _actor.kind.value == "agent") else "manual"

    return deps.store.upsert_edge(
        project,
        _ensure_node_id(deps.store, project, src, source=source, actor=actor_id),
        _ensure_node_id(deps.store, project, dst, source=source, actor=actor_id),
        type,
        attrs,
        source=source,
        actor=actor_id,
    )


@capability(
    registry,
    name="graph_guide",
    description="Full AI graph-building conventions (loaded on demand by agents, §9.20)",
)
def graph_guide() -> dict:
    return {"guide": ai_guide.guide_text()}


# ---------- Read operations ----------


@capability(
    registry, name="query_graph", description="Query a project graph (filterable by label/keyword)"
)
def query_graph(project: str, label: str = "", keyword: str = "", limit: int = 200) -> dict:
    return _require_deps().store.query(project, label=label or None, keyword=keyword, limit=limit)


@capability(
    registry, name="get_subgraph", description="Neighbor expansion from a node (adjustable depth)"
)
def get_subgraph(project: str, node_id: str, depth: int = 1) -> dict:
    return _require_deps().store.subgraph(project, node_id, depth)


@capability(registry, name="graph_stats", description="Graph stats: node/edge counts by label/type")
def graph_stats(project: str) -> dict:
    return _require_deps().store.stats(project)


@capability(registry, name="list_projects", description="Projects that already have graph data")
def list_projects() -> list[str]:
    return _require_deps().store.list_projects()


@capability(
    registry,
    name="engine_info",
    description="Current engine and degraded state (data source for the engine badge)",
)
async def engine_info() -> dict:
    deps = _require_deps()
    engine, name = await deps.adapter.resolve()
    return {"engine": name, "healthy": await engine.health()}


@capability(
    registry,
    name="drop_project_graph",
    description="Delete all nodes and edges of a project",
    reversible=False,
)
def drop_project_graph(project: str) -> dict:
    return _require_deps().store.drop_project(project)


# ---------- Planned tools ----------


@capability(
    registry,
    name="expand_neighbors",
    description="Neighbor expansion: grow edges from a node by depth, "
    "with optional edge-type filter",
)
def expand_neighbors(project: str, node_id: str, depth: int = 1, edge_filter: str = "") -> dict:
    return _require_deps().store.neighbors(project, node_id, depth=depth, edge_filter=edge_filter)


@capability(
    registry, name="find_path", description="Find a short path a→b in the graph (bidirectional BFS)"
)
def find_path(project: str, a: str, b: str, max_hops: int = 4, edge_filter: str = "") -> dict:
    return _require_deps().store.find_path(
        project, a, b, max_hops=max_hops, edge_filter=edge_filter
    )


@capability(
    registry,
    name="set_nodes",
    description="Batch write/update nodes (fewer AI pipeline round trips)",
)
def set_nodes(project: str, nodes: list[dict]) -> dict:
    ai_guide.validate_nodes_batch(project, nodes)
    deps = _require_deps()
    out = []
    for n in nodes:
        out.append(
            deps.store.upsert_node(
                project,
                n["label"],
                n["name"],
                n.get("qualified_name", ""),
                n.get("attrs"),
                source="ai",
                actor="agent.batch",
            )
        )
    return {"project": project, "count": len(out), "nodes": out}


@capability(
    registry,
    name="set_relationships",
    description="Batch write/update relationships (placeholder nodes auto-created)",
)
def set_relationships(project: str, relations: list[dict]) -> dict:
    ai_guide.validate_relations_batch(project, relations)
    deps = _require_deps()
    out = []
    for r in relations:
        src = r["src"]
        dst = r["dst"]
        out.append(
            deps.store.upsert_edge(
                project,
                _ensure_node_id(deps.store, project, src, source="ai", actor="agent.batch"),
                _ensure_node_id(deps.store, project, dst, source="ai", actor="agent.batch"),
                r["type"],
                r.get("attrs"),
                source="ai",
                actor="agent.batch",
            )
        )
    return {"project": project, "count": len(out), "edges": out}


@capability(
    registry,
    name="merge_nodes",
    description="Merge two nodes: keep is preserved, drop's edges migrate to keep",
)
def merge_nodes(project: str, keep: str, drop: str) -> dict:
    return _require_deps().store.merge_nodes(project, keep, drop)


@capability(registry, name="export_subgraph", description="Export a subgraph (JSON/CYPHER)")
def export_subgraph(project: str, node_id: str, depth: int = 2, format: str = "json") -> dict:
    return _require_deps().store.export_subgraph(project, node_id, depth=depth, fmt=format)
