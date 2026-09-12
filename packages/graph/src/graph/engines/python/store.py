"""In-memory graph store with optional zstd/sqlite persistence
(layout lives in layout.py).

Responsibilities:
- Hold nodes/edges in memory with a qualified-name index and adjacency map
- Export/import a shareable graph.db (sqlite; optional .zst compression is
  up to the caller)
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Node:
    id: str
    name: str
    label: str
    file_path: str = ""
    qualified_name: str = ""
    start_line: int = 0
    end_line: int = 0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    size: float = 1.0
    color: str = ""
    in_calls: int = 0
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    source: str
    target: str
    type: str = "CALLS"
    weight: float = 1.0
    attrs: dict[str, Any] = field(default_factory=dict)


class GraphStore:
    """Graph store for a single project."""

    def __init__(self, project: str):
        self.project = project
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self.meta: dict[str, Any] = {"mode": "moderate", "repo_path": ""}
        self._lock = threading.RLock()
        self._adj_out: dict[str, list[Edge]] = {}
        self._adj_in: dict[str, list[Edge]] = {}
        self._qn_index: dict[str, str] = {}

    def clear(self) -> None:
        with self._lock:
            self.nodes.clear()
            self.edges.clear()
            self._adj_out.clear()
            self._adj_in.clear()
            self._qn_index.clear()

    def add_node(self, node: Node) -> None:
        with self._lock:
            self.nodes[node.id] = node
            if node.qualified_name:
                self._qn_index[node.qualified_name] = node.id
            elif node.name:
                self._qn_index[node.name] = node.id

    def add_edge(self, edge: Edge) -> None:
        with self._lock:
            if edge.source not in self.nodes or edge.target not in self.nodes:
                return
            self.edges.append(edge)
            self._adj_out.setdefault(edge.source, []).append(edge)
            self._adj_in.setdefault(edge.target, []).append(edge)
            self.nodes[edge.target].in_calls += 1

    def rebuild_adj(self) -> None:
        with self._lock:
            self._adj_out.clear()
            self._adj_in.clear()
            for n in self.nodes.values():
                n.in_calls = 0
            for e in self.edges:
                self._adj_out.setdefault(e.source, []).append(e)
                self._adj_in.setdefault(e.target, []).append(e)
                if e.target in self.nodes:
                    self.nodes[e.target].in_calls += 1

    def find_by_qn(self, qn: str) -> Node | None:
        # Same lock for reads and writes (the R4 boundary lock test caught this):
        # the index/adjacency structures share one RLock with the write side.
        with self._lock:
            nid = self._qn_index.get(qn)
            if nid:
                return self.nodes.get(nid)
            # Suffix fuzzy match
            for k, nid2 in self._qn_index.items():
                if k.endswith(qn) or qn.endswith(k):
                    return self.nodes.get(nid2)
        return None

    def layout_payload(self, max_nodes: int = 5000) -> dict[str, Any]:
        with self._lock:
            nodes = list(self.nodes.values())
            total = len(nodes)
            # Quota: keep structural nodes (File/Folder/Module...) so the graph
            # does not degrade to Functions only and render in a single color.
            structural = [
                n
                for n in nodes
                if n.label in ("File", "Folder", "Module", "Package", "Project", "Section")
            ]
            others = [
                n
                for n in nodes
                if n.label not in ("File", "Folder", "Module", "Package", "Project", "Section")
            ]
            others.sort(key=lambda n: n.in_calls, reverse=True)
            struct_budget = min(len(structural), max(80, max_nodes // 5))
            rest_budget = max(0, max_nodes - struct_budget)
            structural.sort(key=lambda n: n.in_calls, reverse=True)
            picked = structural[:struct_budget] + others[:rest_budget]
            keep = {n.id for n in picked}
            edges = [e for e in self.edges if e.source in keep and e.target in keep]
            return {
                "nodes": [
                    {
                        "id": n.id,
                        "name": n.name,
                        "label": n.label,
                        "x": n.x,
                        "y": n.y,
                        "z": n.z,
                        "file_path": n.file_path,
                        "qualified_name": n.qualified_name or n.name,
                        "start_line": n.start_line,
                        "end_line": n.end_line,
                        "size": n.size,
                        "color": n.color,
                        "in_calls": n.in_calls,
                        **n.attrs,
                    }
                    for n in picked
                ],
                "edges": [
                    {
                        "source": e.source,
                        "target": e.target,
                        "type": e.type,
                        "weight": e.weight,
                    }
                    for e in edges
                ],
                "total_nodes": total,
            }

    def schema(self) -> dict[str, Any]:
        with self._lock:
            labels: dict[str, int] = {}
            etypes: dict[str, int] = {}
            for n in self.nodes.values():
                labels[n.label] = labels.get(n.label, 0) + 1
            for e in self.edges:
                etypes[e.type] = etypes.get(e.type, 0) + 1
            return {
                "node_labels": [{"label": k, "count": v} for k, v in sorted(labels.items())],
                "edge_types": [{"type": k, "count": v} for k, v in sorted(etypes.items())],
            }

    def persist(self, path: Path) -> None:
        """Write a shareable graph.db (sqlite); optional .zst compression is up to the caller."""
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT)")
            conn.execute("CREATE TABLE nodes (id TEXT PRIMARY KEY, payload TEXT)")
            conn.execute("CREATE TABLE edges (id INTEGER PRIMARY KEY, payload TEXT)")
            with self._lock:
                conn.execute(
                    "INSERT INTO meta VALUES (?, ?)",
                    ("project", self.project),
                )
                conn.execute(
                    "INSERT INTO meta VALUES (?, ?)",
                    ("meta", json.dumps(self.meta, ensure_ascii=False)),
                )
                for n in self.nodes.values():
                    conn.execute(
                        "INSERT INTO nodes VALUES (?, ?)",
                        (
                            n.id,
                            json.dumps(
                                {
                                    "id": n.id,
                                    "name": n.name,
                                    "label": n.label,
                                    "file_path": n.file_path,
                                    "qualified_name": n.qualified_name,
                                    "start_line": n.start_line,
                                    "end_line": n.end_line,
                                    "x": n.x,
                                    "y": n.y,
                                    "z": n.z,
                                    "size": n.size,
                                    "color": n.color,
                                    "in_calls": n.in_calls,
                                    "attrs": n.attrs,
                                },
                                ensure_ascii=False,
                            ),
                        ),
                    )
                for i, e in enumerate(self.edges):
                    conn.execute(
                        "INSERT INTO edges VALUES (?, ?)",
                        (
                            i,
                            json.dumps(
                                {
                                    "source": e.source,
                                    "target": e.target,
                                    "type": e.type,
                                    "weight": e.weight,
                                    "attrs": e.attrs,
                                },
                                ensure_ascii=False,
                            ),
                        ),
                    )
            conn.commit()
        finally:
            conn.close()

    def load(self, path: Path) -> None:
        # Outer lock: clear/add_node each take the RLock, so the whole load is
        # atomic and cannot tear.
        conn = sqlite3.connect(str(path))
        try:
            with self._lock:
                self.clear()
                for row in conn.execute("SELECT k, v FROM meta"):
                    if row[0] == "meta":
                        self.meta = json.loads(row[1])
                for row in conn.execute("SELECT payload FROM nodes"):
                    d = json.loads(row[0])
                    self.add_node(
                        Node(
                            id=d["id"],
                            name=d["name"],
                            label=d["label"],
                            file_path=d.get("file_path", ""),
                            qualified_name=d.get("qualified_name", ""),
                            start_line=int(d.get("start_line") or 0),
                            end_line=int(d.get("end_line") or 0),
                            x=float(d.get("x") or 0),
                            y=float(d.get("y") or 0),
                            z=float(d.get("z") or 0),
                            size=float(d.get("size") or 1),
                            color=d.get("color") or "",
                            in_calls=int(d.get("in_calls") or 0),
                            attrs=d.get("attrs") or {},
                        )
                    )
                for row in conn.execute("SELECT payload FROM edges"):
                    d = json.loads(row[0])
                    self.add_edge(
                        Edge(
                            source=d["source"],
                            target=d["target"],
                            type=d.get("type", "CALLS"),
                            weight=float(d.get("weight") or 1),
                            attrs=d.get("attrs") or {},
                        )
                    )
                self.rebuild_adj()
        finally:
            conn.close()
