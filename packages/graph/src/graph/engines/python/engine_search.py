"""GraphEngine search, code snippets, and path tracing (mixin).

self is always a GraphEngine (uses _store/_lock/meta).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_DEFAULT_SEARCH_LIMIT = 200

_CODE_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java"}

_TRACE_EDGE_TYPES = {
    "calls": {"CALLS"},
    "data_flow": {"CALLS", "DEFINES", "CONTAINS"},
    "cross_service": {"CROSS_HTTP_CALLS", "CROSS_ASYNC", "CROSS_CHANNEL", "CROSS_SHARED_SYMBOL"},
}


class SearchMixin:
    """Node retrieval, grep-augmented search, snippets, and call-chain tracing."""

    def fetch_layout(
        self, project: str, *, max_nodes: int = 5000, graph: str = "code"
    ) -> dict[str, Any]:
        return self._store(project).layout_payload(max_nodes=max_nodes)

    def get_graph_schema(self, project: str) -> dict[str, Any]:
        return self._store(project).schema()

    def search_graph(
        self,
        project: str,
        *,
        query: str = "",
        name_pattern: str = "",
        semantic_query: str = "",
        label: str | None = None,
        limit: int = _DEFAULT_SEARCH_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        limit = min(max(1, limit or _DEFAULT_SEARCH_LIMIT), _DEFAULT_SEARCH_LIMIT)
        offset = max(0, offset)
        store = self._store(project)
        q = (query or semantic_query or "").lower().strip()
        pat = name_pattern.strip()
        scored: list[tuple[float, dict]] = []
        for n in store.nodes.values():
            if label and n.label != label:
                continue
            hay = f"{n.name} {n.qualified_name} {n.file_path} {n.label}".lower()
            score = 0.0
            if q:
                if q in hay:
                    score += 5.0 + (10.0 if n.name.lower() == q else 0)
                for tok in q.split():
                    if tok in hay:
                        score += 1.5
                # Coarse BM25 approximation: term frequency + in-degree
                score += min(3.0, n.in_calls * 0.1)
            if pat:
                try:
                    if not re.search(pat, n.name) and not re.search(pat, n.qualified_name or ""):
                        if not q:
                            continue
                    else:
                        score += 8.0
                except re.error:
                    if pat.lower() not in hay:
                        continue
                    score += 4.0
            if not q and not pat:
                score = 1.0 + n.in_calls * 0.05
            if score <= 0:
                continue
            scored.append(
                (
                    score,
                    {
                        "id": n.id,
                        "name": n.name,
                        "label": n.label,
                        "qualified_name": n.qualified_name,
                        "file_path": n.file_path,
                        "score": round(score, 3),
                        "in_calls": n.in_calls,
                        **{
                            k: v
                            for k, v in n.attrs.items()
                            if k.startswith(
                                ("cyclo", "cogni", "loop", "alloc", "unguard", "linear", "trans")
                            )
                        },
                    },
                )
            )
        scored.sort(key=lambda x: x[0], reverse=True)
        total = len(scored)
        page = [x[1] for x in scored[offset : offset + limit]]
        return {
            "results": page,
            "items": page,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        }

    def search_code(
        self,
        project: str,
        *,
        pattern: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        """grep augmentation: merge hits into function nodes and rank by importance."""
        store = self._store(project)
        root = Path(store.meta.get("repo_path") or "")
        hits: list[dict[str, Any]] = []
        if not root.exists() or not pattern:
            return {"results": [], "has_more": False}
        try:
            rx = re.compile(pattern)
        except re.error:
            rx = re.compile(re.escape(pattern))

        file_hits: dict[str, list[dict]] = {}
        budget = 2000
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _CODE_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    file_hits.setdefault(rel, []).append({"line": i, "text": line.strip()[:240]})
                    budget -= 1
                    if budget <= 0:
                        break
            if budget <= 0:
                break

        # Merge hits into functions
        for n in store.nodes.values():
            if n.label not in ("Function", "Method", "Class"):
                continue
            fh = file_hits.get(n.file_path)
            if not fh:
                continue
            matched = [
                h
                for h in fh
                if (not n.start_line or h["line"] >= n.start_line)
                and (not n.end_line or h["line"] <= n.end_line)
            ]
            if not matched:
                continue
            hits.append(
                {
                    "qualified_name": n.qualified_name,
                    "name": n.name,
                    "file_path": n.file_path,
                    "label": n.label,
                    "in_calls": n.in_calls,
                    "matches": matched[:10],
                    "importance": n.in_calls + len(matched),
                }
            )
        hits.sort(key=lambda x: x["importance"], reverse=True)
        limit = min(max(1, limit), 200)
        page = hits[:limit]
        return {
            "results": page,
            "total": len(hits),
            "has_more": len(hits) > limit,
            "limit": limit,
        }

    def get_code_snippet(self, project: str, qualified_name: str) -> dict[str, Any]:
        store = self._store(project)
        node = store.find_by_qn(qualified_name)
        if not node:
            return {"error": "symbol_not_found", "qualified_name": qualified_name}
        root = Path(store.meta.get("repo_path") or "")
        path = root / node.file_path if root.exists() else None
        code = ""
        if path and path.exists():
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            s = max(0, (node.start_line or 1) - 1)
            e = node.end_line or (s + 40)
            code = "\n".join(lines[s:e])
        return {
            "qualified_name": node.qualified_name,
            "file_path": node.file_path,
            "start_line": node.start_line,
            "end_line": node.end_line,
            "code": code,
            "attrs": node.attrs,
        }

    def trace_path(
        self,
        project: str,
        *,
        start: str = "",
        symbol: str = "",
        direction: str = "both",
        depth: int = 3,
        kind: str = "calls",
    ) -> dict[str, Any]:
        store = self._store(project)
        sym = start or symbol
        node = store.find_by_qn(sym)
        if not node:
            # Fall back to short name
            for n in store.nodes.values():
                if n.name == sym:
                    node = n
                    break
        if not node:
            return {"error": "symbol_not_found", "symbol": sym}

        edge_types = _TRACE_EDGE_TYPES.get(kind, {"CALLS"})

        visited: set[str] = set()
        paths: list[list[str]] = []
        nodes_out: list[dict] = []
        edges_out: list[dict] = []

        def risk(hops: int) -> str:
            if hops <= 1:
                return "LOW"
            if hops == 2:
                return "MEDIUM"
            if hops == 3:
                return "HIGH"
            return "CRITICAL"

        def walk(nid: str, trail: list[str], hops: int, forward: bool) -> None:
            if hops > depth or nid in visited and hops > 0:
                return
            visited.add(nid)
            n = store.nodes.get(nid)
            if n:
                nodes_out.append(
                    {
                        "id": n.id,
                        "name": n.name,
                        "qualified_name": n.qualified_name,
                        "label": n.label,
                    }
                )
            adj = store._adj_out.get(nid, []) if forward else store._adj_in.get(nid, [])
            for e in adj:
                if e.type not in edge_types and kind != "data_flow":
                    if kind == "calls" and e.type != "CALLS":
                        continue
                nxt = e.target if forward else e.source
                edges_out.append(
                    {
                        "source": e.source,
                        "target": e.target,
                        "type": e.type,
                        "risk": risk(hops + 1),
                    }
                )
                new_trail = trail + [nxt]
                if hops + 1 >= depth:
                    paths.append(new_trail)
                walk(nxt, new_trail, hops + 1, forward)

        if direction in ("downstream", "both", "outgoing"):
            walk(node.id, [node.id], 0, True)
        visited.clear()
        if direction in ("upstream", "both", "incoming"):
            walk(node.id, [node.id], 0, False)

        return {
            "start": node.qualified_name or node.name,
            "kind": kind,
            "direction": direction,
            "depth": depth,
            "nodes": nodes_out[:500],
            "edges": edges_out[:1000],
            "paths": paths[:100],
            "risk_summary": {
                "CRITICAL": sum(1 for e in edges_out if e.get("risk") == "CRITICAL"),
                "HIGH": sum(1 for e in edges_out if e.get("risk") == "HIGH"),
                "MEDIUM": sum(1 for e in edges_out if e.get("risk") == "MEDIUM"),
                "LOW": sum(1 for e in edges_out if e.get("risk") == "LOW"),
            },
        }
