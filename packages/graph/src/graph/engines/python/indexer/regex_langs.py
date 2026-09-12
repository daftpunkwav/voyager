"""Go / Rust / Java / Kotlin indexing: unified regex channel
(types + functions + call sites).
"""

from __future__ import annotations

import re

from ..store import Edge, GraphStore, Node
from .helpers import _complexity_attrs, _module_qn, _nid
from .patterns import (
    CALL_RE,
    GO_FN_RE,
    GO_TYPE_RE,
    JAVA_CLASS_RE,
    JAVA_FN_RE,
    RS_FN_RE,
    RS_STRUCT_RE,
)

__all__ = [
    "GO_FN_RE",
    "GO_TYPE_RE",
    "JAVA_CLASS_RE",
    "JAVA_FN_RE",
    "RS_FN_RE",
    "RS_STRUCT_RE",
    "index_regex_defs",
]

_SKIP_FN_NAMES = {"if", "for", "while", "switch", "catch", "return", "new"}


def index_regex_defs(
    store: GraphStore,
    text: str,
    rel: str,
    module_id: str,
    qn_to_id: dict[str, str],
    call_sites: list[tuple[str, str]],
    *,
    fn_re: re.Pattern[str],
    type_re: re.Pattern[str] | None,
    type_label: str,
) -> None:
    mod = _module_qn(store.project, rel)
    lines = text.splitlines()
    if type_re:
        for m in type_re.finditer(text):
            name = m.group(1)
            # java interface → Interface
            label = type_label
            ctx = text[max(0, m.start() - 40) : m.start()]
            if "interface" in ctx:
                label = "Interface"
            qn = f"{mod}.{name}"
            if qn in qn_to_id:
                continue
            nid = _nid(store.project, qn)
            line = text[: m.start()].count("\n") + 1
            store.add_node(
                Node(
                    id=nid,
                    name=name,
                    label=label,
                    file_path=rel,
                    qualified_name=qn,
                    start_line=line,
                    end_line=line,
                )
            )
            qn_to_id[qn] = nid
            store.add_edge(Edge(source=module_id, target=nid, type="DEFINES"))

    for m in fn_re.finditer(text):
        name = m.group(1)
        if name in _SKIP_FN_NAMES:
            continue
        qn = f"{mod}.{name}"
        if qn in qn_to_id:
            continue
        nid = _nid(store.project, qn)
        line = text[: m.start()].count("\n") + 1
        chunk = "\n".join(lines[max(0, line - 1) : line + 40])
        store.add_node(
            Node(
                id=nid,
                name=name,
                label="Function",
                file_path=rel,
                qualified_name=qn,
                start_line=line,
                end_line=line + 40,
                attrs=_complexity_attrs(chunk),
            )
        )
        qn_to_id[qn] = nid
        store.add_edge(Edge(source=module_id, target=nid, type="DEFINES"))
        for cm in CALL_RE.finditer(chunk):
            callee = cm.group(1)
            if callee != name:
                call_sites.append((nid, callee))
