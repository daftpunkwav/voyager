"""Markdown indexing: atx/setext headings → Section nodes."""

from __future__ import annotations

from ..store import Edge, GraphStore, Node
from .helpers import _module_qn, _nid
from .patterns import MD_HEADING_RE, MD_SETEXT_RE


def index_markdown(
    store: GraphStore,
    text: str,
    rel: str,
    module_id: str,
    qn_to_id: dict[str, str],
) -> None:
    seen: set[str] = set()
    for m in MD_HEADING_RE.finditer(text):
        title = m.group(2).strip()
        if not title or title in seen:
            continue
        seen.add(title)
        line = text[: m.start()].count("\n") + 1
        qn = f"{_module_qn(store.project, rel)}.#{title}"
        nid = _nid(store.project, qn)
        store.add_node(
            Node(
                id=nid,
                name=title[:200],
                label="Section",
                file_path=rel,
                qualified_name=qn,
                start_line=line,
                end_line=line,
                attrs={"level": len(m.group(1))},
            )
        )
        qn_to_id[qn] = nid
        store.add_edge(Edge(source=module_id, target=nid, type="DEFINES"))

    for m in MD_SETEXT_RE.finditer(text):
        title = m.group(1).strip()
        if not title or title.startswith("#") or title in seen:
            continue
        seen.add(title)
        line = text[: m.start()].count("\n") + 1
        qn = f"{_module_qn(store.project, rel)}.#{title}"
        nid = _nid(store.project, qn)
        store.add_node(
            Node(
                id=nid,
                name=title[:200],
                label="Section",
                file_path=rel,
                qualified_name=qn,
                start_line=line,
                end_line=line,
                attrs={"level": 1 if m.group(2).startswith("=") else 2},
            )
        )
        qn_to_id[qn] = nid
        store.add_edge(Edge(source=module_id, target=nid, type="DEFINES"))
