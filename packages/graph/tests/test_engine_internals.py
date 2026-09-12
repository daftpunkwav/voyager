"""Characterization tests for GraphEngine search/query/trace/architecture
surfaces.
"""

import tempfile

from graph.engines.python.engine import GraphEngine


def _engine_with_repo(files: dict[str, str], project: str = "demo") -> GraphEngine:
    eng = GraphEngine(data_root=tempfile.mkdtemp())
    root = eng.data_root / "repo"
    root.mkdir(parents=True)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    eng.index_repository(str(root), name=project, persistence=False)
    return eng


class TestSearchAndQuery:
    def test_search_graph_scoring_and_label(self) -> None:
        eng = _engine_with_repo(
            {
                "a.py": "def importer():\n    helper()\n\ndef helper():\n    return 1\n",
            }
        )
        out = eng.search_graph("demo", query="helper")
        names = [r["name"] for r in out["results"]]
        assert "helper" in names and out["results"][0]["name"] == "helper"  # exact name ranks first
        by_label = eng.search_graph("demo", label="Function", query="")
        assert all(r["label"] == "Function" for r in by_label["results"])

    def test_cypher_subset_match_nodes(self) -> None:
        eng = _engine_with_repo({"m.py": "def run():\n    pass\n"})
        out = eng.query_graph("demo", "MATCH (n:Function) RETURN n LIMIT 10")
        assert out["row_count"] >= 1
        assert any(r.get("name") == "run" for r in out["rows"])

    def test_trace_path_calls(self) -> None:
        eng = _engine_with_repo({"t.py": "def a():\n    b()\n\ndef b():\n    pass\n"})
        out = eng.trace_path("demo", start="demo.t.py.a", kind="calls")
        src_names = {n["name"] for n in out["nodes"]}
        assert "b" in src_names  # a -> calls -> b is traced

    def test_architecture_hotspots(self) -> None:
        eng = _engine_with_repo(
            {
                # hub is called from three places -> in-degree >= 3 makes it a hotspot
                "h.py": (
                    "def hub():\n    pass\n"
                    "def a():\n    hub()\ndef b():\n    hub()\ndef c():\n    hub()\n"
                ),
            }
        )
        arch = eng.get_architecture("demo")
        assert any(h["name"] == "hub" for h in arch["hotspots"])
