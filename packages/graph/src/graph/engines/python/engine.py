"""Graph engine: Python fallback aligned with the native C engine's
tool surface.

Search/snippet/tracing live in engine_search.py, the Cypher subset in
engine_query.py, and the architecture surface in engine_architecture.py;
this module keeps only engine lifecycle, indexing entry points, cross-repo
heuristics, and unified tool dispatch (call).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from .engine_architecture import ArchitectureMixin
from .engine_query import QueryMixin
from .engine_search import SearchMixin
from .indexer import index_repository
from .store import GraphStore

log = logging.getLogger("graph.engine.python")

_CYPHER_ROW_CAP = 100_000

_ENGINE_FLAVOR = "python"


class GraphEngine(SearchMixin, QueryMixin, ArchitectureMixin):
    """In-process engine; can also be wrapped by an HTTP sidecar (no global singleton, see server.main)."""

    flavor = _ENGINE_FLAVOR

    def __init__(self, data_root: str | Path | None = None):
        self.data_root = Path(data_root) if data_root else Path.cwd() / "data"
        self.graphs_dir = self.data_root / "graph-db"
        self.graphs_dir.mkdir(parents=True, exist_ok=True)
        self._projects: dict[str, GraphStore] = {}
        self._cross_edges: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    # ---------- Lifecycle and health ----------

    def health(self) -> bool:
        return True

    def _store(self, project: str) -> GraphStore:
        with self._lock:
            if project not in self._projects:
                store = GraphStore(project)
                db = self.graphs_dir / f"{project}.db"
                if db.exists():
                    try:
                        store.load(db)
                    except Exception:
                        # Fall back to an empty graph on load failure, but log it:
                        # swallowing the error would leave an inexplicably empty graph.
                        log.warning(
                            "failed to load persisted graph data; "
                            "project %s starts from an empty graph",
                            project,
                            exc_info=True,
                        )
                self._projects[project] = store
            return self._projects[project]

    def drop_project(self, project: str) -> dict[str, Any]:
        """Delete the in-memory graph and its persisted files (.db / .db.zst)."""
        name = (project or "").strip()
        removed_files: list[str] = []
        with self._lock:
            self._projects.pop(name, None)
            for path in (
                self.graphs_dir / f"{name}.db",
                self.graphs_dir / f"{name}.db.zst",
            ):
                if path.exists():
                    try:
                        path.unlink()
                        removed_files.append(str(path))
                    except OSError:
                        pass
        return {"project": name, "removed_files": removed_files}

    # ---------- Indexing and persistence ----------

    def index_repository(
        self,
        repo_path: str,
        *,
        mode: str = "moderate",
        name: str | None = None,
        target_projects: list[str] | None = None,
        persistence: bool = True,
        should_abandon: Any = None,
    ) -> dict[str, Any]:
        if mode == "cross-repo-intelligence":
            return self._cross_repo(target_projects or [])

        project = name or Path(repo_path).name
        store = self._store(project)
        # Indexing is serialized per project; different projects may run in
        # parallel (stores are isolated by name).
        with self._lock:
            project_lock = getattr(store, "_index_lock", None)
            if project_lock is None:
                project_lock = threading.Lock()
                store._index_lock = project_lock
        with project_lock:
            if callable(should_abandon) and should_abandon():
                return {
                    "project": project,
                    "mode": mode,
                    "abandoned": True,
                    "node_count": 0,
                    "edge_count": 0,
                }
            result = index_repository(store, repo_path, mode=mode)
            if callable(should_abandon) and should_abandon():
                result["abandoned"] = True
                return result
            if persistence:
                db_path = self.graphs_dir / f"{project}.db"
                store.persist(db_path)
                # Optional zst: keep only .db when zstandard is unavailable.
                zst = Path(str(db_path) + ".zst")
                try:
                    import zstandard as zstd  # type: ignore

                    cctx = zstd.ZstdCompressor(level=3)
                    with open(db_path, "rb") as src, open(zst, "wb") as dst:
                        dst.write(cctx.compress(src.read()))
                    result["persistence_path"] = str(zst)
                except Exception:
                    result["persistence_path"] = str(db_path)
        return result

    # ---------- Cross-repo heuristics and export ----------

    def _cross_repo(self, projects: list[str]) -> dict[str, Any]:
        """Generate cross-repo edges via same-name symbol heuristics."""
        edges: list[dict[str, Any]] = []
        stores = [self._store(p) for p in projects if p]
        name_map: dict[str, list[tuple[str, str]]] = {}
        for st in stores:
            for n in st.nodes.values():
                if n.label in ("Function", "Method", "Class"):
                    name_map.setdefault(n.name.lower(), []).append(
                        (st.project, n.qualified_name or n.name)
                    )
        for _name, locs in name_map.items():
            projs = {p for p, _ in locs}
            if len(projs) < 2:
                continue
            uniq = list({(p, q) for p, q in locs})
            for i in range(min(len(uniq), 8)):
                for j in range(i + 1, min(len(uniq), 8)):
                    if uniq[i][0] == uniq[j][0]:
                        continue
                    edges.append(
                        {
                            "source_engine": uniq[i][0],
                            "target_engine": uniq[j][0],
                            "source_symbol": uniq[i][1],
                            "target_symbol": uniq[j][1],
                            "relation": "CROSS_SHARED_SYMBOL",
                            "type": "CROSS_SHARED_SYMBOL",
                            "weight": 1.0,
                        }
                    )
                    if len(edges) >= 500:
                        break
                if len(edges) >= 500:
                    break
            if len(edges) >= 500:
                break

        with self._lock:
            self._cross_edges = edges
        return {"mode": "cross-repo-intelligence", "edge_count": len(edges), "edges": edges}

    def export_graph(self, project: str) -> dict[str, Any]:
        """Export the full graph (nodes + edges) for canonical-store sync; not capped by the search limit."""
        store = self._store(project)
        with self._lock:
            nodes = [
                {
                    "id": n.id,
                    "name": n.name,
                    "label": n.label,
                    "qualified_name": n.qualified_name,
                    "file_path": n.file_path,
                    "attrs": dict(n.attrs),
                }
                for n in store.nodes.values()
            ]
            edges = [
                {
                    "src": e.source,
                    "dst": e.target,
                    "type": e.type,
                    "attrs": dict(e.attrs),
                }
                for e in store.edges
            ]
        return {"nodes": nodes, "edges": edges}

    def list_cross_edges(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._cross_edges)

    # ---------- Unified tool dispatch (single mapping shared by client and HTTP sidecar) ----------

    def call(self, name: str, args: dict[str, Any]) -> Any:
        """New tools only need one branch here, avoiding duplicated mappings in client/server."""
        if name == "index_repository":
            return self.index_repository(
                args.get("repo_path") or ".",
                mode=args.get("mode") or "moderate",
                name=args.get("name"),
                target_projects=args.get("target_projects"),
                persistence=bool(args.get("persistence", True)),
            )
        if name == "search_graph":
            return self.search_graph(
                args["project"],
                query=args.get("query") or "",
                name_pattern=args.get("name_pattern") or "",
                semantic_query=args.get("semantic_query") or "",
                label=args.get("label"),
                limit=int(args.get("limit") or 200),
                offset=int(args.get("offset") or 0),
            )
        if name == "search_code":
            return self.search_code(
                args["project"],
                pattern=args.get("pattern") or args.get("query") or "",
                limit=int(args.get("limit") or 50),
            )
        if name == "get_code_snippet":
            return self.get_code_snippet(args["project"], args.get("qualified_name") or "")
        if name == "trace_path":
            return self.trace_path(
                args["project"],
                start=args.get("start") or args.get("symbol") or "",
                symbol=args.get("symbol") or "",
                direction=args.get("direction") or "both",
                depth=int(args.get("depth") or 3),
                kind=args.get("kind") or args.get("type") or "calls",
            )
        if name == "query_graph":
            return self.query_graph(
                args.get("project") or "",
                args.get("query") or "",
                limit=min(int(args.get("limit") or _CYPHER_ROW_CAP), _CYPHER_ROW_CAP),
            )
        if name == "export_graph":
            return self.export_graph(args["project"])
        if name == "get_graph_schema":
            return self.get_graph_schema(args["project"])
        if name == "fetch_layout":
            return self.fetch_layout(args["project"], max_nodes=int(args.get("max_nodes") or 5000))
        if name == "get_architecture":
            return self.get_architecture(args["project"], aspects=args.get("aspects"))
        if name == "drop_project":
            return self.drop_project(args.get("project") or args.get("name") or "")
        raise ValueError(f"unknown tool: {name}")
