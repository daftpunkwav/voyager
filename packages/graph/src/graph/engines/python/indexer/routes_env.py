"""Route decorator and environment variable scanning (Python/JS
route declarations, env assignments and usages).
"""

from __future__ import annotations

from ..store import Edge, GraphStore, Node
from .helpers import _module_qn, _nid
from .patterns import ENV_ASSIGN_RE, ENV_USAGE_RE, JS_ROUTE_RE, PY_ROUTE_RE


def index_routes(
    store: GraphStore,
    text: str,
    rel: str,
    module_id: str,
    qn_to_id: dict[str, str],
    ext: str,
) -> None:
    mod = _module_qn(store.project, rel)
    patterns = []
    if ext in {".py", ".pyi"}:
        patterns.append(PY_ROUTE_RE)
    if ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        patterns.append(JS_ROUTE_RE)
    for cre in patterns:
        for m in cre.finditer(text):
            path = m.group(1)
            qn = f"{mod}.__route__.{path}"
            if qn in qn_to_id:
                continue
            nid = _nid(store.project, qn)
            store.add_node(
                Node(
                    id=nid,
                    name=path,
                    label="Route",
                    file_path=rel,
                    qualified_name=qn,
                    start_line=text[: m.start()].count("\n") + 1,
                    attrs={"path": path},
                )
            )
            qn_to_id[qn] = nid
            store.add_edge(Edge(source=module_id, target=nid, type="DEFINES"))


def index_env_file(
    store: GraphStore,
    text: str,
    module_id: str,
    qn_to_id: dict[str, str],
) -> None:
    for m in ENV_ASSIGN_RE.finditer(text):
        key, val = m.group(1), m.group(2)
        qn = f"env.{key}"
        nid = _nid(store.project, qn)
        existing_id = qn_to_id.get(qn)
        if existing_id is not None:
            # The node may already have been created by the usage branch (without
            # value info): backfill the value preview
            existing = store.nodes.get(existing_id)
            if existing is not None and "value_preview" not in (existing.attrs or {}):
                existing.attrs = {**existing.attrs, "value_preview": val[:80]}
            continue
        store.add_node(
            Node(
                id=nid,
                name=key,
                label="EnvVar",
                qualified_name=qn,
                attrs={"value_preview": val[:80]},
            )
        )
        qn_to_id[qn] = nid
        store.add_edge(Edge(source=module_id, target=nid, type="DEFINES"))


def index_env_usages(
    store: GraphStore,
    text: str,
    module_id: str,
    qn_to_id: dict[str, str],
) -> None:
    for m in ENV_USAGE_RE.finditer(text):
        key = m.group(1) or m.group(2) or m.group(3)
        if not key:
            continue
        qn = f"env.{key}"
        if qn not in qn_to_id:
            nid = _nid(store.project, qn)
            store.add_node(Node(id=nid, name=key, label="EnvVar", qualified_name=qn))
            qn_to_id[qn] = nid
        store.add_edge(Edge(source=module_id, target=qn_to_id[qn], type="USAGE"))
