"""Python indexing: ast-parsed Class/Function/Method/Variable plus
decorators and call sites.
"""

from __future__ import annotations

import ast

from ..store import Edge, GraphStore, Node
from .helpers import _complexity_attrs, _decorator_str, _module_qn, _nid
from .patterns import CALL_RE, DECORATOR_NAME_RE


def index_python(
    store: GraphStore,
    text: str,
    rel: str,
    module_id: str,
    qn_to_id: dict[str, str],
    call_sites: list[tuple[str, str]],
    import_edges: list[tuple[str, str]],
) -> None:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return
    mod = _module_qn(store.project, rel)

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                raw = (
                    f"{node.module}.{alias.name}"
                    if isinstance(node, ast.ImportFrom) and node.module
                    else alias.name
                )
                import_edges.append((module_id, raw))

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            qn = (
                f"{mod}.{'.'.join(self.stack + [node.name])}"
                if self.stack
                else f"{mod}.{node.name}"
            )
            nid = _nid(store.project, qn)
            src = ast.get_source_segment(text, node) or ""
            decs = [_decorator_str(d) for d in node.decorator_list]
            store.add_node(
                Node(
                    id=nid,
                    name=node.name,
                    label="Class",
                    file_path=rel,
                    qualified_name=qn,
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                    attrs={**_complexity_attrs(src), "decorators": decs},
                )
            )
            qn_to_id[qn] = nid
            parent = qn_to_id.get(f"{mod}.{'.'.join(self.stack)}") if self.stack else module_id
            store.add_edge(Edge(source=parent or module_id, target=nid, type="DEFINES"))
            for d in node.decorator_list:
                _add_decorator(store, d, nid, rel, mod, qn_to_id)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._fn(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._fn(node)

        def _fn(self, node: ast.AST) -> None:
            name = getattr(node, "name", "fn")
            if self.stack:
                qn = f"{mod}.{'.'.join(self.stack)}.{name}"
                label = "Method"
            else:
                qn = f"{mod}.{name}"
                label = "Function"
            nid = _nid(store.project, qn)
            src = ast.get_source_segment(text, node) or ""
            decs = [_decorator_str(d) for d in getattr(node, "decorator_list", [])]
            store.add_node(
                Node(
                    id=nid,
                    name=name,
                    label=label,
                    file_path=rel,
                    qualified_name=qn,
                    start_line=getattr(node, "lineno", 0),
                    end_line=getattr(node, "end_lineno", 0) or 0,
                    attrs={**_complexity_attrs(src), "decorators": decs},
                )
            )
            qn_to_id[qn] = nid
            parent = qn_to_id.get(f"{mod}.{'.'.join(self.stack)}") if self.stack else module_id
            store.add_edge(
                Edge(
                    source=parent or module_id,
                    target=nid,
                    type="DEFINES_METHOD" if label == "Method" else "DEFINES",
                )
            )
            for d in getattr(node, "decorator_list", []):
                _add_decorator(store, d, nid, rel, mod, qn_to_id)
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    callee = _call_name(child.func)
                    if callee:
                        call_sites.append((nid, callee))

        def visit_Assign(self, node: ast.Assign) -> None:
            if self.stack:
                return
            for t in node.targets:
                self._var(t, node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            if self.stack:
                return
            self._var(node.target, node)

        def _var(self, target: ast.AST, node: ast.AST) -> None:
            if not isinstance(target, ast.Name):
                return
            name = target.id
            # Skip trivial module-level bindings, mirroring the native engine's
            # preference for "meaningful declarations"
            if name in {"__all__", "__version__", "__author__"}:
                return
            qn = f"{mod}.{name}"
            if qn in qn_to_id:
                return
            nid = _nid(store.project, qn)
            store.add_node(
                Node(
                    id=nid,
                    name=name,
                    label="Variable",
                    file_path=rel,
                    qualified_name=qn,
                    start_line=getattr(node, "lineno", 0),
                    end_line=getattr(node, "end_lineno", 0) or 0,
                    attrs={"is_exported": not name.startswith("_")},
                )
            )
            qn_to_id[qn] = nid
            store.add_edge(Edge(source=module_id, target=nid, type="DEFINES"))

    Visitor().visit(tree)


def _add_decorator(
    store: GraphStore,
    dec: ast.AST,
    target_id: str,
    rel: str,
    mod: str,
    qn_to_id: dict[str, str],
) -> None:
    raw = _decorator_str(dec)
    m = DECORATOR_NAME_RE.match("@" + raw if not raw.startswith("@") else raw)
    name = (m.group(1) if m else raw).split("(")[0].strip("@")
    if not name:
        return
    qn = f"{mod}.@decorator.{name}"
    nid = qn_to_id.get(qn) or _nid(store.project, qn)
    if qn not in qn_to_id:
        store.add_node(
            Node(
                id=nid,
                name=name,
                label="Decorator",
                file_path=rel,
                qualified_name=qn,
            )
        )
        qn_to_id[qn] = nid
    store.add_edge(Edge(source=nid, target=target_id, type="DECORATES", attrs={"decorator": name}))


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


# Shared with jsts/regex_langs to reuse the same call-scanning semantics
CALL_SCANNER = CALL_RE
