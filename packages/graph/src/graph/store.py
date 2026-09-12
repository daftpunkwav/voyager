"""Canonical graph store: one graph, distinguishable provenance.

Responsibilities:
- Persist nodes/edges in one SQLite graph keyed by natural key
  (project, label, qualified_name), making upserts idempotent
- Read primitives (query / subgraph / stats) and provenance tracking by
  source ("code" / "ai" / "manual")
- Delegate coarse-grained operations to operations.py, keeping the public
  API unchanged

- Engine output from programmatic pipelines arrives via the adapter layer
  (source="code");
- AI pipeline agents write via set_node/set_relationship in capabilities.py
  (source="ai"), which delegate to upsert_node/upsert_edge here;
- User-created nodes carry source="manual".
The natural key (project, label, qualified_name) makes upserts idempotent.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from . import operations
from .columns import _EDGE_COLS, _NODE_COLS, _row

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id             TEXT PRIMARY KEY,
    project        TEXT NOT NULL,
    label          TEXT NOT NULL,
    name           TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    attrs          TEXT NOT NULL DEFAULT '{}',
    source         TEXT NOT NULL DEFAULT 'manual',
    actor          TEXT NOT NULL DEFAULT '',
    updated_ts     REAL NOT NULL,
    UNIQUE (project, label, qualified_name)
);
CREATE INDEX IF NOT EXISTS idx_nodes_project ON nodes(project, label);
CREATE TABLE IF NOT EXISTS edges (
    id         TEXT PRIMARY KEY,
    project    TEXT NOT NULL,
    src        TEXT NOT NULL,
    dst        TEXT NOT NULL,
    type       TEXT NOT NULL,
    attrs      TEXT NOT NULL DEFAULT '{}',
    source     TEXT NOT NULL DEFAULT 'manual',
    actor      TEXT NOT NULL DEFAULT '',
    updated_ts REAL NOT NULL,
    UNIQUE (project, src, dst, type)
);
CREATE INDEX IF NOT EXISTS idx_edges_project ON edges(project, type);
"""


def _node_id(project: str, label: str, qualified_name: str) -> str:
    return hashlib.sha1(f"{project}{label}{qualified_name}".encode()).hexdigest()[:16]


def _edge_id(project: str, src: str, dst: str, type_: str) -> str:
    return hashlib.sha1(f"{project}{src}{dst}{type_}".encode()).hexdigest()[:16]


class GraphStore:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        # One lock for reads and writes: synchronous capability handlers run
        # on worker threads via to_thread, concurrent with the index pipeline
        # (event-loop thread); a bare read on the single connection would mean
        # cross-thread concurrent use. RLock rather than Lock because
        # upsert_node -> get_node and merge_nodes -> _node_by_id nest locks
        # on the same thread.
        self._lock = threading.RLock()

    def upsert_node(
        self,
        project: str,
        label: str,
        name: str,
        qualified_name: str = "",
        attrs: dict | None = None,
        *,
        source: str = "manual",
        actor: str = "",
    ) -> dict[str, Any]:
        qn = qualified_name or name
        nid = _node_id(project, label, qn)
        with self._lock:
            self._conn.execute(
                "INSERT INTO nodes (id, project, label, name, qualified_name, attrs,"
                " source, actor, updated_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(project, label, qualified_name) DO UPDATE SET"
                " name=excluded.name, attrs=excluded.attrs, source=excluded.source,"
                " actor=excluded.actor, updated_ts=excluded.updated_ts",
                (
                    nid,
                    project,
                    label,
                    name,
                    qn,
                    json.dumps(attrs or {}, ensure_ascii=False),
                    source,
                    actor,
                    time.time(),
                ),
            )
            self._conn.commit()
        node = self.get_node(project, label, qn)
        if node is None:  # unreachable: the upsert above guarantees the row
            raise KeyError(nid)
        return node

    def get_node(self, project: str, label: str, qualified_name: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                f"SELECT {','.join(_NODE_COLS)} FROM nodes"
                " WHERE project=? AND label=? AND qualified_name=?",
                (project, label, qualified_name),
            ).fetchone()
        return _row(_NODE_COLS, row) if row else None

    def upsert_edge(
        self,
        project: str,
        src: str,
        dst: str,
        type_: str,
        attrs: dict | None = None,
        *,
        source: str = "manual",
        actor: str = "",
    ) -> dict[str, Any]:
        eid = _edge_id(project, src, dst, type_)
        with self._lock:
            self._conn.execute(
                "INSERT INTO edges (id, project, src, dst, type, attrs, source, actor,"
                " updated_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(project, src, dst, type) DO UPDATE SET"
                " attrs=excluded.attrs, source=excluded.source, actor=excluded.actor,"
                " updated_ts=excluded.updated_ts",
                (
                    eid,
                    project,
                    src,
                    dst,
                    type_,
                    json.dumps(attrs or {}, ensure_ascii=False),
                    source,
                    actor,
                    time.time(),
                ),
            )
            self._conn.commit()
            row = self._conn.execute(
                f"SELECT {','.join(_EDGE_COLS)} FROM edges WHERE id=?", (eid,)
            ).fetchone()
        return _row(_EDGE_COLS, row)

    def query(
        self, project: str, *, label: str | None = None, keyword: str = "", limit: int = 200
    ) -> dict[str, Any]:
        conds, params = ["project = ?"], [project]
        if label:
            conds.append("label = ?")
            params.append(label)
        if keyword:
            conds.append("(name LIKE ? OR qualified_name LIKE ?)")
            params += [f"%{keyword}%", f"%{keyword}%"]
        with self._lock:
            nodes = [
                _row(_NODE_COLS, r)
                for r in self._conn.execute(
                    f"SELECT {','.join(_NODE_COLS)} FROM nodes WHERE {' AND '.join(conds)} LIMIT ?",
                    (*params, limit),
                )
            ]
            node_ids = {n["id"] for n in nodes}
            edges = []
            for r in self._conn.execute(
                f"SELECT {','.join(_EDGE_COLS)} FROM edges WHERE project = ?", (project,)
            ):
                e = _row(_EDGE_COLS, r)
                if e["src"] in node_ids and e["dst"] in node_ids:
                    edges.append(e)
        return {"project": project, "nodes": nodes, "edges": edges}

    def subgraph(self, project: str, node_id: str, depth: int = 1) -> dict[str, Any]:
        """Expand neighbors from node_id up to the given depth (near-end of the two-level load)."""
        seen_nodes: dict[str, dict] = {}
        seen_edges: dict[str, dict] = {}
        frontier = {node_id}
        with self._lock:
            all_edges = [
                _row(_EDGE_COLS, r)
                for r in self._conn.execute(
                    f"SELECT {','.join(_EDGE_COLS)} FROM edges WHERE project = ?", (project,)
                )
            ]
            for _ in range(max(depth, 0) + 1):
                if not frontier:
                    break
                qmarks = ",".join("?" for _ in frontier)
                for r in self._conn.execute(
                    f"SELECT {','.join(_NODE_COLS)} FROM nodes"
                    f" WHERE project = ? AND id IN ({qmarks})",
                    (project, *frontier),
                ):
                    n = _row(_NODE_COLS, r)
                    seen_nodes[n["id"]] = n
                nxt = set()
                for e in all_edges:
                    if e["src"] in frontier or e["dst"] in frontier:
                        seen_edges[e["id"]] = e
                        for end in (e["src"], e["dst"]):
                            if end not in seen_nodes:
                                nxt.add(end)
                frontier = nxt
        return {
            "project": project,
            "nodes": list(seen_nodes.values()),
            "edges": list(seen_edges.values()),
        }

    def stats(self, project: str) -> dict[str, Any]:
        with self._lock:
            nodes = self._conn.execute(
                "SELECT label, COUNT(*) FROM nodes WHERE project = ? GROUP BY label",
                (project,),
            ).fetchall()
            edges = self._conn.execute(
                "SELECT type, COUNT(*) FROM edges WHERE project = ? GROUP BY type",
                (project,),
            ).fetchall()
        return {
            "project": project,
            "nodes_by_label": {r[0]: r[1] for r in nodes},
            "edges_by_type": {r[0]: r[1] for r in edges},
            "total_nodes": sum(r[1] for r in nodes),
            "total_edges": sum(r[1] for r in edges),
        }

    def list_projects(self) -> list[str]:
        with self._lock:
            return [
                r[0]
                for r in self._conn.execute("SELECT DISTINCT project FROM nodes ORDER BY project")
            ]

    def list_code_projects(self) -> list[str]:
        """Projects that have programmatic pipeline output (candidates for cross-repo relations)."""
        with self._lock:
            return [
                r[0]
                for r in self._conn.execute(
                    "SELECT DISTINCT project FROM nodes WHERE source = 'code'"
                )
            ]

    def neighbors(
        self, project: str, node_id: str, *, depth: int = 1, edge_filter: str = ""
    ) -> dict[str, Any]:
        """Expand neighbors up to depth with optional edge-type filter (see operations)."""
        return operations.neighbors(self, project, node_id, depth=depth, edge_filter=edge_filter)

    def find_path(
        self, project: str, a: str, b: str, *, max_hops: int = 4, edge_filter: str = ""
    ) -> dict[str, Any]:
        """BFS shortest path from a to b (see operations)."""
        return operations.find_path(self, project, a, b, max_hops=max_hops, edge_filter=edge_filter)

    def merge_nodes(self, project: str, keep: str, drop: str) -> dict[str, Any]:
        """Merge two nodes (see operations)."""
        return operations.merge_nodes(self, project, keep, drop)

    def export_subgraph(
        self, project: str, node_id: str, *, depth: int = 2, fmt: str = "json"
    ) -> dict[str, Any]:
        """Export a subgraph as JSON/CYPHER (see operations)."""
        return operations.export_subgraph(self, project, node_id, depth=depth, fmt=fmt)

    def _node_by_id(self, project: str, node_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                f"SELECT {','.join(_NODE_COLS)} FROM nodes WHERE project=? AND id=?",
                (project, node_id),
            ).fetchone()
        return _row(_NODE_COLS, row) if row else None

    def _edge_by_id(self, project: str, edge_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                f"SELECT {','.join(_EDGE_COLS)} FROM edges WHERE project=? AND id=?",
                (project, edge_id),
            ).fetchone()
        return _row(_EDGE_COLS, row) if row else None

    def drop_project(self, project: str) -> dict[str, int]:
        with self._lock:
            n = self._conn.execute("DELETE FROM nodes WHERE project = ?", (project,)).rowcount
            e = self._conn.execute("DELETE FROM edges WHERE project = ?", (project,)).rowcount
            self._conn.commit()
        return {"nodes": n, "edges": e}

    def purge_meta(self, project: str, keep_qn: set[str] | None = None) -> dict[str, int]:
        """Drop meta-pipeline derived data, keeping AI/manual output (call before L0 rebuild).

        - Deletes edges with source='meta' in the project;
        - Deletes Resource nodes whose qualified_name is not in keep_qn
          (AI-written edges on them become dangling and are tolerated by
          the read layer);
        - Non-Resource nodes (AI-created concepts/entities) are always kept.
        """
        keep = keep_qn or set()
        with self._lock:
            e = self._conn.execute(
                "DELETE FROM edges WHERE project = ? AND source = 'meta'", (project,)
            ).rowcount
            if keep:
                rows = self._conn.execute(
                    "SELECT id FROM nodes WHERE project = ? AND label = 'Resource'"
                    f" AND qualified_name NOT IN ({','.join('?' * len(keep))})",
                    (project, *keep),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT id FROM nodes WHERE project = ? AND label = 'Resource'", (project,)
                ).fetchall()
            n = 0
            for (nid,) in rows:
                n += self._conn.execute("DELETE FROM nodes WHERE id = ?", (nid,)).rowcount
            self._conn.commit()
        return {"nodes": n, "edges": e}

    def cross_edges(self, edge_type: str = "CROSS_REPO") -> list[dict[str, Any]]:
        """Cross-project relation edges (cross-repo space), merged into the L0 view."""
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {','.join(_EDGE_COLS)} FROM edges"
                " WHERE project = 'cross-repo' AND type = ?",
                (edge_type,),
            ).fetchall()
        return [_row(_EDGE_COLS, r) for r in rows]

    def close(self) -> None:
        self._conn.close()
