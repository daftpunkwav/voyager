"""Import boundary scanner: an automated lock over the dependency
matrix, on top of the import-linter contracts (see import-linter.ini).

AST-level static check with zero third-party dependencies; covers agent/ and
packages/ (including their tests). packages/host is not scanned: the assembly
root is the only place allowed to import every domain. apps/ and docs/ are
outside this lock. Rules inspect only the full module names of
Import/ImportFrom nodes; relative imports (level > 0) are unconstrained.

Layout note: every workspace member is an installed top-level package (src
layout: packages/<name>/src/<name>/, platform under packages/platform/<pkg>/
src/platform_<pkg>/). A file is therefore judged by where it lives (its scope,
packages/<owner>/...) while the imported names are plain top-level packages:
the business set is read from the packages/ directory itself, so a new domain
is covered without touching this test.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_SCAN_ROOTS = ("agent", "packages")
_SKIP_DIRS = {"__pycache__", "venv", ".venv", "node_modules"}


def _business_packages() -> frozenset[str]:
    """Import names of every business package: the directories under packages/
    other than the platform group (domains, gateway, host, scaffold)."""
    return frozenset(
        p.name
        for p in (ROOT / "packages").iterdir()
        if p.is_dir() and p.name != "platform" and not p.name.startswith(".")
    )


_BUSINESS = _business_packages()


def _imported_modules(tree: ast.AST):
    """Stream of (lineno, fully qualified module name); top-level absolute imports only."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module


def _violations(scope: tuple[str, ...], source: str, display: str) -> list[str]:
    """Judge violations by the scope the file lives in; returns a list of
    "path:lineno: reason" entries.

    - Within agent: any business package (domains, gateway, host) is forbidden;
    - Within packages/<domain>: agent / apps are forbidden, as is any other
      business package (host, sibling domains);
    - Within packages/platform: agent / apps and every business package are
      forbidden.
    The retired ``packages.*`` namespace path is rejected everywhere.
    """
    problems: list[str] = []
    tree = ast.parse(source, filename=display)
    for lineno, module in _imported_modules(tree):
        top = module.split(".")[0]
        why = ""
        if scope[0] == "agent":
            if top == "packages" or top in _BUSINESS:
                why = f"agent must not import {top} (domain / composition-root implementation)"
        elif scope[0] == "packages":
            owner = scope[1] if len(scope) > 1 else ""
            if owner == "host":
                pass  # composition root may import everything
            elif owner == "platform":
                if top in ("agent", "apps", "packages") or top in _BUSINESS:
                    why = f"platform must not import {top}"
            elif top in ("agent", "apps"):
                why = f"{owner or '*'} must not import {top}"
            elif top == "packages":
                why = f"{owner or '*'} must not import packages.* (retired namespace path)"
            elif top in _BUSINESS and top != owner:
                why = f"{owner or '*'} must not import {top} (cross-domain / composition root)"
        if why:
            problems.append(f"{display}:{lineno}: {why}")
    return problems


def _repo_py_files() -> list[Path]:
    out: list[Path] = []
    for root in _SCAN_ROOTS:
        for p in (ROOT / root).rglob("*.py"):
            if _SKIP_DIRS & set(p.parts):
                continue
            out.append(p)
    return sorted(out)


def test_business_set_matches_layout() -> None:
    """The business set is read from disk: the scaffold, the composition root
    and the gateway are in it, the platform group is not."""
    assert {"host", "gateway", "_template"} <= _BUSINESS
    assert "platform" not in _BUSINESS


def test_current_repo_has_zero_violations() -> None:
    problems: list[str] = []
    for path in _repo_py_files():
        rel = path.relative_to(ROOT)
        # packages needs the owner segment (packages/<owner>/...) to judge
        # cross-domain imports; agent uses the first segment
        scope = rel.parts[:2] if rel.parts[0] == "packages" else rel.parts[:1]
        problems.extend(_violations(scope, path.read_text(encoding="utf-8"), rel.as_posix()))
    assert not problems, "cross-boundary imports found (§12 dependency matrix):\n" + "\n".join(
        problems
    )


def test_checker_catches_deliberate_bad_imports() -> None:
    """Sanity check of the lock itself: synthetic bad imports must be caught (no
    bad imports written into production files)."""
    assert len(_violations(("agent",), "import notes\n", "f.py")) == 1
    assert len(_violations(("agent",), "from host.bridge import x\n", "f.py")) == 1
    assert (
        len(_violations(("packages", "platform"), "from notes.wiring import wire\n", "f.py")) == 1
    )
    assert len(_violations(("packages", "platform"), "import apps.web\n", "f.py")) == 1
    # packages/<domain>: a sibling domain / host is a violation; the same
    # domain (including deeper modules) and platform facilities are allowed
    assert (
        len(_violations(("packages", "sources"), "from graph.store import GraphStore\n", "f.py"))
        == 1
    )
    assert (
        len(
            _violations(
                ("packages", "sources"), "from host.bridge import make_domain_tools\n", "f.py"
            )
        )
        == 1
    )
    assert (
        _violations(("packages", "sources"), "from sources.modules.doc import store\n", "f.py")
        == []
    )
    assert (
        _violations(("packages", "sources"), "from platform_capability import Registry\n", "f.py")
        == []
    )
    # The retired namespace path is rejected in every scope
    assert (
        len(
            _violations(
                ("packages", "sources"), "from packages.sources.rest import create_app\n", "f.py"
            )
        )
        == 1
    )
    # Failure messages carry path and line number
    msg = _violations(("agent",), "import packages\n", "agent/bad.py")[0]
    assert "agent/bad.py" in msg and ":1:" in msg
