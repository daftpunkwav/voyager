"""Programmatic pipeline, repo relation analysis: cross-repo
dependency edges.

Repos sharing import targets or tech stacks get CROSS_REPO edges written to
the canonical store (source="code"). Coverage is source-level relations only;
semantic similarity (embeddings) is future work.
"""

from __future__ import annotations

from typing import Any

from ...store import GraphStore

_EXTERNAL_HINTS = (
    "fastapi",
    "django",
    "flask",
    "react",
    "vue",
    "sqlalchemy",
    "pydantic",
    "numpy",
    "pandas",
    "httpx",
    "click",
    "rich",
)


def relate_repos(store: GraphStore, projects: list[str]) -> dict[str, Any]:
    """For each repo pair, shared external deps/stack yield CROSS_REPO edges
    (idempotent upserts)."""
    created = 0
    deps_by_project = {p: _external_deps(store, p) for p in projects}
    node_ids = {
        p: store.upsert_node("cross-repo", "Project", p, p, source="code", actor="pipeline.relate")[
            "id"
        ]
        for p in projects
    }
    for i, a in enumerate(projects):
        for b in projects[i + 1 :]:
            shared = sorted(deps_by_project[a] & deps_by_project[b])
            if not shared:
                continue
            for dep in shared:
                store.upsert_edge(
                    "cross-repo",
                    node_ids[a],
                    node_ids[b],
                    "CROSS_REPO",
                    {"shared_dependency": dep},
                    source="code",
                    actor="pipeline.relate",
                )
                created += 1
    return {
        "projects": projects,
        "cross_edges": created,
        "shared": {
            f"{a}~{b}": sorted(deps_by_project[a] & deps_by_project[b])
            for i, a in enumerate(projects)
            for b in projects[i + 1 :]
            if deps_by_project[a] & deps_by_project[b]
        },
    }


def _external_deps(store: GraphStore, project: str) -> set[str]:
    graph = store.query(project, limit=100000)
    deps: set[str] = set()
    for node in graph["nodes"]:
        target = str(node["attrs"].get("import_target") or "")
        root = target.split(".")[0].lower()
        if root in _EXTERNAL_HINTS:
            deps.add(root)
    return deps
