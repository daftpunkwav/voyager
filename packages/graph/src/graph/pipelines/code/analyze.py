"""Programmatic pipeline, source-code analysis: engine parses a
repo and syncs the result into the canonical graph store.

Responsibilities:
- Run engine indexing over a repo through the adapter (C/Python differences
  hidden) and export the output into the canonical store
  (source="code", actor=engine name)
- Map engine node ids to canonical store ids on edge export (the two id
  spaces differ)
- Trigger repo relation analysis automatically after indexing
- Keep per-node synchronous store upserts off the event loop (worker
  thread) so HTTP/SSE never stalls

The adapter layer hides C/Python differences; engine output lands in the
store via export (source="code", actor=engine name). After indexing, repo
relation analysis runs automatically; edge export maps engine node ids to
canonical store ids (the two id spaces differ).

This module runs on the event loop (wiring awaits it directly), so the
per-node synchronous store upserts (commit = fsync) must go to a worker
thread; otherwise HTTP/SSE for the whole process stalls while a large
repository is being indexed.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ...engines.adapter import EngineAdapter
from ...store import GraphStore
from .relate import relate_repos


async def analyze_repo(
    adapter: EngineAdapter,
    store: GraphStore,
    *,
    project: str,
    repo_path: str,
    mode: str = "moderate",
) -> dict[str, Any]:
    """Index a repository: engine parse -> export to the canonical store
    -> cross-repo relations -> stats."""
    engine, engine_name = await adapter.resolve()
    result = await engine.index_repository(repo_path, name=project, mode=mode)
    exported = await _export_to_canonical(engine, engine_name, store, project)
    projects = await asyncio.to_thread(_indexed_projects, store, project)
    related = await asyncio.to_thread(relate_repos, store, projects)
    return {
        "project": project,
        "engine": engine_name,
        "engine_result": result,
        **exported,
        "relate": related,
    }


def _indexed_projects(store: GraphStore, current: str) -> list[str]:
    """Projects worth relating: the current project plus others with code nodes (source=code)."""
    projects = {current}
    rows = store.list_code_projects()
    projects.update(rows)
    projects.discard("cross-repo")
    return sorted(projects)


async def _export_to_canonical(
    engine: Any, engine_name: str, store: GraphStore, project: str
) -> dict[str, int]:
    """Export the engine's internal graph into the canonical store (idempotent upserts).

    Engine node ids and canonical store ids are separate spaces: upsert nodes
    first while recording an engine-id -> canonical-id map, rewrite edge
    endpoints through the map, and drop edges with dangling endpoints.
    """
    graph = await engine.call("export_graph", {"project": project})
    nodes = graph.get("nodes") or graph.get("results") or []
    edges = graph.get("edges") or []
    id_map: dict[str, str] = {}
    for n in nodes:
        qn = str(n.get("qualified_name") or n.get("qualifiedName") or n.get("name") or "")
        row = await asyncio.to_thread(
            store.upsert_node,
            project,
            str(n.get("label") or "Unknown"),
            str(n.get("name") or qn),
            qn,
            n.get("attrs") or {},
            source="code",
            actor=f"engine.{engine_name}",
        )
        engine_id = str(n.get("id") or "")
        if engine_id:
            id_map[engine_id] = row["id"]
    mapped = 0
    for e in edges:
        src = id_map.get(str(e.get("src") or e.get("from") or ""))
        dst = id_map.get(str(e.get("dst") or e.get("to") or ""))
        if not src or not dst:
            continue
        await asyncio.to_thread(
            store.upsert_edge,
            project,
            src,
            dst,
            str(e.get("type") or "RELATED"),
            e.get("attrs") or {},
            source="code",
            actor=f"engine.{engine_name}",
        )
        mapped += 1
    return {"exported_nodes": len(nodes), "exported_edges": mapped}
