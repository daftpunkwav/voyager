"""JS/TS indexing: interfaces/types/classes/functions/arrow
functions/top-level variables and methods (heuristic).
"""

from __future__ import annotations

from ..store import Edge, GraphStore, Node
from .helpers import _complexity_attrs, _module_qn, _nid
from .patterns import (
    CALL_RE,
    JS_ARROW_RE,
    JS_CLASS_RE,
    JS_FN_RE,
    JS_IMPORT_RE,
    JS_INTERFACE_RE,
    JS_METHOD_RE,
    JS_TYPE_RE,
    JS_VAR_RE,
)


def index_js_ts(
    store: GraphStore,
    text: str,
    rel: str,
    module_id: str,
    qn_to_id: dict[str, str],
    call_sites: list[tuple[str, str]],
    import_edges: list[tuple[str, str]],
    ext: str,
) -> None:
    mod = _module_qn(store.project, rel)
    lines = text.splitlines()
    func_names: set[str] = set()

    for m in JS_IMPORT_RE.finditer(text):
        target = m.group(1) or m.group(2) or m.group(3) or ""
        if target:
            import_edges.append((module_id, target))

    def _add(label: str, name: str, start: int, end: int, attrs: dict | None = None) -> str:
        qn = f"{mod}.{name}"
        if qn in qn_to_id:
            return qn_to_id[qn]
        nid = _nid(store.project, qn)
        line = text[:start].count("\n") + 1
        store.add_node(
            Node(
                id=nid,
                name=name,
                label=label,
                file_path=rel,
                qualified_name=qn,
                start_line=line,
                end_line=max(line, end),
                attrs=attrs or {},
            )
        )
        qn_to_id[qn] = nid
        store.add_edge(Edge(source=module_id, target=nid, type="DEFINES"))
        return nid

    if ext in {".ts", ".tsx"}:
        for m in JS_INTERFACE_RE.finditer(text):
            _add("Interface", m.group(1), m.start(), m.end())
        for m in JS_TYPE_RE.finditer(text):
            _add("Type", m.group(1), m.start(), m.end())

    for m in JS_CLASS_RE.finditer(text):
        _add("Class", m.group(1), m.start(), m.end(), _complexity_attrs(""))

    for m in JS_FN_RE.finditer(text):
        name = m.group(1)
        func_names.add(name)
        line = text[: m.start()].count("\n") + 1
        chunk = "\n".join(lines[max(0, line - 1) : line + 40])
        nid = _add("Function", name, m.start(), m.end(), _complexity_attrs(chunk))
        for cm in CALL_RE.finditer(chunk):
            callee = cm.group(1)
            if callee != name:
                call_sites.append((nid, callee))

    for m in JS_ARROW_RE.finditer(text):
        name = m.group(1)
        func_names.add(name)
        line = text[: m.start()].count("\n") + 1
        chunk = "\n".join(lines[max(0, line - 1) : line + 40])
        nid = _add("Function", name, m.start(), m.end(), _complexity_attrs(chunk))
        for cm in CALL_RE.finditer(chunk):
            callee = cm.group(1)
            if callee != name:
                call_sites.append((nid, callee))

    # Class methods (indentation heuristic)
    skip_method = {
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "function",
        "return",
    }
    for m in JS_METHOD_RE.finditer(text):
        name = m.group(1)
        if name in skip_method or name in func_names:
            continue
        # Require a class declaration earlier in the text
        before = text[max(0, m.start() - 800) : m.start()]
        if "class " not in before:
            continue
        func_names.add(name)
        line = text[: m.start()].count("\n") + 1
        chunk = "\n".join(lines[max(0, line - 1) : line + 30])
        qn = f"{mod}.{name}"
        if qn in qn_to_id:
            continue
        nid = _nid(store.project, qn)
        store.add_node(
            Node(
                id=nid,
                name=name,
                label="Method",
                file_path=rel,
                qualified_name=qn,
                start_line=line,
                end_line=line + 30,
                attrs=_complexity_attrs(chunk),
            )
        )
        qn_to_id[qn] = nid
        store.add_edge(Edge(source=module_id, target=nid, type="DEFINES_METHOD"))
        for cm in CALL_RE.finditer(chunk):
            callee = cm.group(1)
            if callee != name:
                call_sites.append((nid, callee))

    for m in JS_VAR_RE.finditer(text):
        name = m.group(2)
        exported = bool(m.group(1))
        if name in func_names or name in {"if", "for", "while", "switch"}:
            continue
        qn = f"{mod}.{name}"
        if qn in qn_to_id:
            continue
        _add(
            "Variable",
            name,
            m.start(),
            m.end(),
            {"is_exported": exported},
        )
