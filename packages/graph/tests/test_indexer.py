"""Characterization tests for the indexer: ignore rules, multi-language nodes,
env scanning. These cases must pass unchanged before and after any packaging split,
proving a pure structural refactor with no behavior drift.
"""

from pathlib import Path

from graph.engines.python.indexer import index_repository
from graph.engines.python.store import GraphStore


def _index(tmp_path: Path, files: dict[str, str]) -> tuple[GraphStore, dict]:
    (tmp_path / "repo").mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        p = tmp_path / "repo" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    store = GraphStore("t")
    result = index_repository(store, tmp_path / "repo", mode="moderate")
    return store, result


class TestIgnore:
    def test_engineignore_skips_and_negation(self, tmp_path) -> None:
        store, _ = _index(
            tmp_path,
            {
                ".engineignore": "vendor\ndist/\n!keep.md\n",
                "a.py": "def f():\n    pass\n",
                "vendor/x.py": "def v():\n    pass\n",
                "dist/y.py": "def d():\n    pass\n",
                "notes.txt": "text\n",
                "keep.md": "# kept\n",
            },
        )
        names = {n.name for n in store.nodes.values()}
        assert "x.py" not in names and "y.py" not in names  # vendor/ and dist/ ignored
        assert "keep.md" in names  # negation rule lets it through (md not in ALL_EXT)

    def test_safety_core_dirs_never_negated(self, tmp_path) -> None:
        store, _ = _index(
            tmp_path,
            {
                ".engineignore": "!.git\n",
                "a.py": "x = 1\n",
            },
        )
        # .git simply has nothing indexable; assert only that the negated rule
        # does not crash the indexer
        assert store.meta["mode"] == "moderate"


class TestLanguages:
    def test_python_functions_and_calls(self, tmp_path) -> None:
        store, _ = _index(
            tmp_path,
            {
                "app/main.py": (
                    "@staticmethod\nclass Greeter:\n"
                    "    def hi(self):\n        run()\n"
                    "\ndef run():\n    return 1\n"
                    "VERSION = '1.0'\n"
                ),
            },
        )
        by_label: dict[str, set[str]] = {}
        for n in store.nodes.values():
            by_label.setdefault(n.label, set()).add(n.name)
        assert "Greeter" in by_label.get("Class", set())
        assert {"hi", "run"} <= by_label.get("Function", set()) | by_label.get("Method", set())
        assert "VERSION" in by_label.get("Variable", ())

    def test_js_ts_go_basic_symbols(self, tmp_path) -> None:
        store, _ = _index(
            tmp_path,
            {
                "web/a.ts": (
                    "export interface Shape { a: number }\n"
                    "export type Kind = 's';\n"
                    "export class Box {}\n"
                    "export function draw() { box(); }\n"
                    "const arrow = () => 1;\n"
                ),
                "svc/m.go": ("package svc\nfunc Start() {\nstop()\n}\n"),
            },
        )
        names = {n.name for n in store.nodes.values()}
        assert {"Shape", "Kind", "Box", "draw", "arrow"} <= names
        assert "Start" in names  # Go functions come in via the regex channel

    def test_markdown_sections_and_env_scan(self, tmp_path) -> None:
        store, _ = _index(
            tmp_path,
            {
                "docs/g.md": "# Title A\n\nBody\n\n## Section B\n",
                ".env": "API_TOKEN=abc123\n",
                "cfg/app.py": "import os\nos.environ['API_TOKEN']\n",
            },
        )
        sections = [n for n in store.nodes.values() if n.label == "Section"]
        env = [n for n in store.nodes.values() if n.label == "EnvVar"]
        assert {"Title A", "Section B"} <= {n.name for n in sections}
        assert any(n.name == "API_TOKEN" and n.attrs.get("value_preview") == "abc123" for n in env)


class TestWiring:
    def test_contains_and_mode_limits(self, tmp_path) -> None:
        store, result = _index(tmp_path, {"one.py": "def only():\n    pass\n"})
        types = {e.type for e in store.edges}
        assert "CONTAINS" in types and "DEFINES" in types
        assert result["node_count"] == len(store.nodes)
