"""Lock-discipline boundary tests for SQLite stores: reads and writes must
share one lock.

Because capability sync handlers always run on asyncio.to_thread worker threads,
an unlocked read can observe uncommitted intermediate state written by another
thread. Concurrency discipline enforced only on write paths does not hold up
case by case, so this test turns the discipline into a mechanism:

Every public method of a SQLite store holding self._lock must execute under the
lock (the method body uses `with self._lock` directly; composite methods rely on
RLock reentrancy, following packages/graph/store.py). Private methods (underscore
prefix) are covered by their public callers and are outside this test's scope.

After adding a new store file, register it in _STORE_FILES (an unregistered file
is caught by test_store_inventory_stays_current).
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

_STORE_FILES = [
    "agent/src/agent/memory/episodic.py",
    "agent/src/agent/memory/profile.py",
    "agent/src/agent/memory/semantic.py",
    "agent/src/agent/sessions/store.py",
    "agent/src/agent/runtime/meter_store.py",
    "agent/src/agent/runtime/queue_store.py",
    "agent/src/agent/runtime/trajectory.py",
    "agent/src/agent/runtime/session_index.py",
    "agent/src/agent/tools/workspace/write_journal.py",
    "packages/platform/capability/src/platform_capability/audit_db.py",
    "packages/platform/eventbus/src/platform_eventbus/log.py",
    "packages/platform/secrets/src/platform_secrets/store.py",
    "packages/platform/settings/src/platform_settings/store.py",
    "packages/_template/src/_template/store.py",
    "packages/browser/src/browser/store.py",
    "packages/code_exec/src/code_exec/store.py",
    "packages/graph/src/graph/engines/python/store.py",
    "packages/graph/src/graph/index_queue.py",
    "packages/graph/src/graph/store.py",
    "packages/llm/src/llm/store.py",
    "packages/notes/src/notes/assets.py",
    "packages/notes/src/notes/store.py",
    "packages/office/src/office/store.py",
    "packages/sources/src/sources/modules/doc/store.py",
    "packages/sources/src/sources/modules/repo/store.py",
    "packages/sources/src/sources/modules/web/store.py",
]

#: Contains sqlite3.connect but is not a resident store (each entry carries a reason)
_NON_STORE = {
    "packages/sources/src/sources/migration.py": "one-shot migration, single-threaded at startup",
}

#: (file, class, method) -> exemption reason; for the global close() exemption see below
METHOD_EXEMPT: dict[tuple[str, str, str], str] = {
    (
        "packages/platform/eventbus/src/platform_eventbus/log.py",
        "EventLog",
        "lock",
    ): "returns the lock object itself, for the shared-lock convention",
    (
        "packages/platform/eventbus/src/platform_eventbus/log.py",
        "EventLog",
        "conn",
    ): "property returns the connection object itself (shared-connection convention), runs no queries",
    (
        "packages/platform/secrets/src/platform_secrets/store.py",
        "SecretStore",
        "available",
    ): "property reads the key-material boolean only, never touches the db",
    # Delegates to operations.py, whose function bodies already run
    # `with store._lock`; export_subgraph fetches via the lock-holding
    # store.subgraph and then does pure computation
    (
        "packages/graph/src/graph/store.py",
        "GraphStore",
        "neighbors",
    ): "delegates to operations.neighbors, locked inside operations",
    (
        "packages/graph/src/graph/store.py",
        "GraphStore",
        "find_path",
    ): "delegates to operations.find_path, locked inside operations",
    (
        "packages/graph/src/graph/store.py",
        "GraphStore",
        "merge_nodes",
    ): "delegates to operations.merge_nodes, locked inside operations",
    (
        "packages/graph/src/graph/store.py",
        "GraphStore",
        "export_subgraph",
    ): "delegates to operations.export_subgraph, fetches via the lock-holding store.subgraph",
}
#: Lifecycle-method exemption: shutdown-path and in-flight-query waiting semantics
#: are not verified per domain
LIFECYCLE_EXEMPT = {"close"}


def _lock_attr_names(class_node: ast.ClassDef) -> set[str]:
    """Lock attribute names of the form self.<*lock*> within the class."""
    names: set[str] = set()
    for node in ast.walk(class_node):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                    and "lock" in target.attr
                ):
                    names.add(target.attr)
    return names


def _is_self_lock(expr: ast.expr, lock_names: set[str]) -> bool:
    return (
        isinstance(expr, ast.Attribute)
        and isinstance(expr.value, ast.Name)
        and expr.value.id == "self"
        and expr.attr in lock_names
    )


def _holds_lock(func: ast.AST, lock_names: set[str]) -> bool:
    for node in ast.walk(func):
        if isinstance(node, (ast.With, ast.AsyncWith)) and any(
            _is_self_lock(item.context_expr, lock_names) for item in node.items
        ):
            return True
    return False


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rel = path.relative_to(ROOT).as_posix()
    out: list[str] = []
    for class_node in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        lock_names = _lock_attr_names(class_node)
        if not lock_names:
            continue
        for member in class_node.body:
            if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if member.name.startswith("_") or member.name in LIFECYCLE_EXEMPT:
                continue
            if (rel, class_node.name, member.name) in METHOD_EXEMPT:
                continue
            if not _holds_lock(member, lock_names):
                out.append(
                    f"{rel}:{member.lineno} {class_node.name}.{member.name} does not hold the lock"
                )
    return out


def test_sqlite_store_public_methods_hold_lock() -> None:
    violations: list[str] = []
    for rel in _STORE_FILES:
        violations.extend(_violations(ROOT / rel))
    assert not violations, (
        "SQLite store public methods must read and write under the same lock "
        "(fix pattern: wrap reads in the existing write lock; composite methods "
        "rely on Lock->RLock reentrancy, see packages/graph/src/graph/store.py):\n"
        + "\n".join(violations)
    )


def test_store_inventory_stays_current() -> None:
    """Every new SQLite-connection file must be registered in this test's
    discipline list, preventing another bypass."""
    missing: list[str] = []
    for domain in ("agent", "packages"):
        for path in (ROOT / domain).rglob("*.py"):
            parts = path.parts
            if "tests" in parts or "__pycache__" in parts:
                continue
            if "sqlite3.connect" not in path.read_text(encoding="utf-8", errors="ignore"):
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel not in _STORE_FILES and rel not in _NON_STORE:
                missing.append(rel)
    assert not missing, (
        "These files open SQLite connections but are not registered in the "
        "lock-discipline test (add them to _STORE_FILES or _NON_STORE with a "
        "reason):\n" + "\n".join(missing)
    )
