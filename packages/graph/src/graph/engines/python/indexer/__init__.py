"""Static-analysis indexing: multi-language support package.

Responsibilities:
- Traverse a repository (respecting .engineignore and mode limits) and build
  the structural spine: Project / Branch / Folder / File
- Dispatch per-language parsers (Python ast, JS/TS and regex languages,
  Markdown sections, routes and env vars) to collect symbols, call sites,
  and import edges into the engine store

Target node types align with the native engine:
Project / Branch / Folder / File / Module / Section / Function / Method /
Class / Interface / Type / Variable / Route / Decorator / EnvVar / Macro

- constants.py   extension sets, skipped directories, mode limits;
- patterns.py    all language scan regexes (single source of truth);
- ignore.py      .engineignore (gitignore-style) and file traversal;
- helpers.py     shared helpers for id/qualified_name/complexity/branches;
- markdown_lang / python_lang / jsts / regex_langs / routes_env:
  per-language and cross-cutting concerns.
"""

from __future__ import annotations

from pathlib import Path

from ..layout import force_layout_3d
from ..store import Edge, GraphStore, Node
from .constants import DOC_EXT, MODE_LIMITS
from .helpers import (
    _file_qn,
    _folder_qn,
    _is_test_path,
    _lang_of,
    _module_qn,
    _nid,
    _read_git_branch,
)
from .ignore import iter_source_files
from .jsts import index_js_ts
from .markdown_lang import index_markdown
from .python_lang import index_python
from .regex_langs import (
    GO_FN_RE,
    GO_TYPE_RE,
    JAVA_CLASS_RE,
    JAVA_FN_RE,
    RS_FN_RE,
    RS_STRUCT_RE,
    index_regex_defs,
)
from .routes_env import index_env_file, index_env_usages, index_routes

__all__ = ["index_repository", "iter_source_files"]


def index_repository(
    store: GraphStore,
    repo_path: str | Path,
    *,
    mode: str = "moderate",
) -> dict:
    limits = MODE_LIMITS.get(mode) or MODE_LIMITS["moderate"]
    root = Path(repo_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"repo path does not exist: {root}")

    store.clear()
    store.meta = {"mode": mode, "repo_path": str(root)}

    files = list(iter_source_files(root, limits["max_files"]))
    max_bytes = int(limits["max_bytes"] or 0)

    # —— Pass 1: structure (Project / Branch / Folder / File) ——
    project_qn = store.project
    project_id = _nid(store.project, f"Project:{project_qn}")
    store.add_node(
        Node(
            id=project_id,
            name=store.project,
            label="Project",
            qualified_name=project_qn,
        )
    )
    branch = _read_git_branch(root)
    branch_qn = f"{project_qn}.__branch__.{branch}"
    branch_id = _nid(store.project, branch_qn)
    store.add_node(
        Node(
            id=branch_id,
            name=branch,
            label="Branch",
            qualified_name=branch_qn,
        )
    )
    store.add_edge(Edge(source=project_id, target=branch_id, type="HAS_BRANCH"))

    folder_ids: dict[str, str] = {"": project_id, ".": project_id}
    file_ids: dict[str, str] = {}
    module_ids: dict[str, str] = {}
    qn_to_id: dict[str, str] = {project_qn: project_id}
    call_sites: list[tuple[str, str]] = []
    import_edges: list[tuple[str, str]] = []  # (module_id, target_str)

    dirs: set[str] = set()
    for path in files:
        rel = str(path.relative_to(root)).replace("\\", "/")
        parent = str(Path(rel).parent).replace("\\", "/")
        if parent in (".", ""):
            continue
        cur = parent
        while cur and cur not in (".", "/"):
            dirs.add(cur)
            nxt = str(Path(cur).parent).replace("\\", "/")
            if nxt in (".", cur):
                break
            cur = nxt

    for d in sorted(dirs, key=lambda x: x.count("/")):
        fq = _folder_qn(store.project, d)
        fid = _nid(store.project, f"Folder:{fq}")
        folder_ids[d] = fid
        store.add_node(
            Node(
                id=fid,
                name=Path(d).name,
                label="Folder",
                file_path=d,
                qualified_name=fq,
            )
        )
        qn_to_id[fq] = fid
        parent = str(Path(d).parent).replace("\\", "/")
        parent_id = folder_ids.get(parent if parent not in (".",) else "", project_id)
        store.add_edge(Edge(source=parent_id, target=fid, type="CONTAINS_FOLDER"))

    for path in files:
        rel = str(path.relative_to(root)).replace("\\", "/")
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if max_bytes > 0 and len(raw) > max_bytes:
            raw = raw[:max_bytes]
        text = raw.decode("utf-8", errors="replace")

        file_qn = _file_qn(store.project, rel)
        fid = _nid(store.project, file_qn)
        ext = path.suffix.lower()
        store.add_node(
            Node(
                id=fid,
                name=path.name,
                label="File",
                file_path=rel,
                qualified_name=file_qn,
                attrs={
                    "extension": ext,
                    "language": _lang_of(ext, path.name),
                    "is_test": _is_test_path(rel),
                },
            )
        )
        file_ids[rel] = fid
        qn_to_id[file_qn] = fid
        parent = str(Path(rel).parent).replace("\\", "/")
        parent_id = folder_ids.get("" if parent == "." else parent, project_id)
        store.add_edge(Edge(source=parent_id, target=fid, type="CONTAINS_FILE"))

        # Module (one per parseable file, aligned with the native engine)
        mod_qn = _module_qn(store.project, rel)
        mid = _nid(store.project, f"Module:{mod_qn}")
        store.add_node(
            Node(
                id=mid,
                name=path.name,
                label="Module",
                file_path=rel,
                qualified_name=mod_qn,
            )
        )
        module_ids[rel] = mid
        qn_to_id[mod_qn] = mid
        store.add_edge(Edge(source=fid, target=mid, type="DEFINES"))

        if ext in DOC_EXT:
            index_markdown(store, text, rel, mid, qn_to_id)
        elif ext in {".py", ".pyi"}:
            index_python(store, text, rel, mid, qn_to_id, call_sites, import_edges)
        elif ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            index_js_ts(store, text, rel, mid, qn_to_id, call_sites, import_edges, ext)
        elif ext == ".go":
            index_regex_defs(
                store,
                text,
                rel,
                mid,
                qn_to_id,
                call_sites,
                fn_re=GO_FN_RE,
                type_re=GO_TYPE_RE,
                type_label="Type",
            )
        elif ext == ".rs":
            index_regex_defs(
                store,
                text,
                rel,
                mid,
                qn_to_id,
                call_sites,
                fn_re=RS_FN_RE,
                type_re=RS_STRUCT_RE,
                type_label="Type",
            )
        elif ext in {".java", ".kt", ".kts"}:
            index_regex_defs(
                store,
                text,
                rel,
                mid,
                qn_to_id,
                call_sites,
                fn_re=JAVA_FN_RE,
                type_re=JAVA_CLASS_RE,
                type_label="Class",
            )
        else:
            # Config etc.: keep File+Module; env vars are still scanned below
            pass

        index_routes(store, text, rel, mid, qn_to_id, ext)
        index_env_usages(store, text, mid, qn_to_id)

    # Env file scan (mirrors envscan)
    for path in files:
        name = path.name.lower()
        if name == ".env" or name.startswith(".env.") or name.endswith(".env"):
            rel = str(path.relative_to(root)).replace("\\", "/")
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            mid = module_ids.get(rel)
            if mid:
                index_env_file(store, text, mid, qn_to_id)

    # CALLS
    name_index: dict[str, list[str]] = {}
    for qn, nid in qn_to_id.items():
        short = qn.rsplit(".", 1)[-1]
        name_index.setdefault(short, []).append(nid)

    for caller, callee in call_sites:
        targets = name_index.get(callee) or []
        for tid in targets[:3]:
            if tid != caller:
                store.add_edge(Edge(source=caller, target=tid, type="CALLS"))

    # IMPORTS: no self-loops for targets unresolved to a local module; keep only
    # edges that resolve to a Module in this repo.
    mod_by_suffix: dict[str, str] = {}
    for rel, mid in module_ids.items():
        mod_by_suffix[rel.replace("\\", "/")] = mid
        mod_by_suffix[rel.replace("\\", "/").rsplit(".", 1)[0]] = mid

    for mid, target in import_edges:
        t = target.strip("./")
        hit = None
        for key, tid in mod_by_suffix.items():
            if key.endswith(t.replace(".", "/") + ".py") or key.endswith(
                t.replace(".", "/") + ".ts"
            ):
                hit = tid
                break
            if key.replace("/", ".").endswith(t):
                hit = tid
                break
        if hit and hit != mid:
            store.add_edge(Edge(source=mid, target=hit, type="IMPORTS"))

    # CONTAINS: attach symbols to their File
    for n in list(store.nodes.values()):
        if (
            n.label
            in (
                "Function",
                "Class",
                "Method",
                "Interface",
                "Type",
                "Variable",
                "Section",
                "Route",
                "Decorator",
            )
            and n.file_path in file_ids
        ):
            store.add_edge(Edge(source=file_ids[n.file_path], target=n.id, type="CONTAINS"))

    store.rebuild_adj()
    nodes = list(store.nodes.values())
    edges = list(store.edges)
    force_layout_3d(nodes, edges, iterations=limits["layout_iters"])

    return {
        "project": store.project,
        "mode": mode,
        "node_count": len(store.nodes),
        "edge_count": len(store.edges),
        "repo_path": str(root),
    }
