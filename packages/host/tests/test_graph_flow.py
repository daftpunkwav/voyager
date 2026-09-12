"""Index pipeline integration: HTTP enqueue -> scheduler run to completion
(Python engine, forced inside tests) -> event chain (task.progress/completed plus
graph.engine.fallback) -> query_graph returns nodes and edges; manually created nodes
share the graph with indexed ones; the agent bridge reaches graph tools.
"""

import time

from fastapi.testclient import TestClient
from host.assemble import build


def _make_toy_repo(root) -> str:
    """Build a small python file tree in a tmp directory (main calls helper,
    helper calls utils)."""
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "toy"
    repo.mkdir()
    (repo / "main.py").write_text(
        "import helper\n\ndef run():\n    return helper.go()\n", encoding="utf-8"
    )
    (repo / "helper.py").write_text(
        "import utils\n\ndef go():\n    return utils.answer()\n", encoding="utf-8"
    )
    (repo / "utils.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    return str(repo)


def _wait_job_done(client, job_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        jobs = client.post("/api/graph/capabilities/list_index_jobs", json={}).json()["result"]
        job = next((j for j in jobs if j["id"] == job_id), None)
        if job and job["status"] in ("done", "failed"):
            return job
        time.sleep(0.1)
    raise AssertionError(f"index job timed out: {job_id}")


class TestIndexPipeline:
    def test_full_chain_python_engine(self, tmp_path) -> None:
        """enqueue 202 -> scheduler -> fallback event -> graph has nodes and call
        edges."""
        ws = tmp_path / "ws"
        repo_path = _make_toy_repo(ws)
        app = build(tmp_path / "data", ws)
        backend = app.state.backend
        with TestClient(app) as client:
            resp = client.post(
                "/api/graph/capabilities/enqueue_index",
                json={
                    "project": "toy",
                    "repo_path": repo_path,
                },
            )
            assert resp.status_code == 202  # JobRef (long tasks are only enqueued)
            job_id = resp.json()["job"]["job_id"]

            job = _wait_job_done(client, job_id)
            assert job["status"] == "done", job["error"]
            assert job["error"] == ""

            # Event chain: progress + completion + engine fallback (no C sidecar
            # by default, reported honestly)
            types = [e.type for _, e in backend.log.read_after()]
            assert "task.progress" in types
            assert "task.completed" in types
            assert "graph.engine.fallback" in types

            info = client.post("/api/graph/capabilities/engine_info", json={}).json()["result"]
            assert info["engine"] == "python"  # or the fallback event: both are honest

            graph = client.post(
                "/api/graph/capabilities/query_graph", json={"project": "toy"}
            ).json()["result"]
            names = {n["name"] for n in graph["nodes"]}
            assert {"run", "go", "answer"} <= names  # function nodes made it into the graph
            assert len(graph["edges"]) > 0  # edges too (with id mapping)
            ids = {n["id"] for n in graph["nodes"]}
            assert all(e["src"] in ids and e["dst"] in ids for e in graph["edges"])

            # Manual nodes share the graph with engine nodes; origins remain
            # distinguishable
            created = client.post(
                "/api/graph/capabilities/set_node",
                json={
                    "project": "toy",
                    "label": "Concept",
                    "name": "ReAct pattern",
                },
            ).json()["result"]
            assert created["source"] == "manual"
            code_nodes = [n for n in graph["nodes"] if n["source"] == "code"]
            assert code_nodes

            # Near side of two-level loading: get_subgraph can expand
            fn = next(n for n in graph["nodes"] if n["name"] == "run")
            sub = client.post(
                "/api/graph/capabilities/get_subgraph",
                json={
                    "project": "toy",
                    "node_id": fn["id"],
                    "depth": 1,
                },
            ).json()["result"]
            assert len(sub["nodes"]) >= 1

    def test_queue_cancel_and_manual_project(self, tmp_path) -> None:
        """Queued jobs can be cancelled; a graph can be built under a manually
        named project (no resource library involved)."""
        ws = tmp_path / "ws2"
        repo_path = _make_toy_repo(ws / "another")
        app = build(tmp_path / "data2", ws)
        with TestClient(app) as client:
            # Occupy the scheduler first (concurrency=1): with a long task
            # running, a second queued one can be cancelled
            busy = client.post(
                "/api/graph/capabilities/enqueue_index",
                json={
                    "project": "busy",
                    "repo_path": repo_path,
                },
            ).json()["job"]["job_id"]
            assert busy
            jid = client.post(
                "/api/graph/capabilities/enqueue_index",
                json={
                    "project": "later",
                    "repo_path": repo_path,
                    "priority": 200,
                },
            ).json()["job"]["job_id"]
            out = client.post("/api/graph/capabilities/cancel_index", json={"job_id": jid}).json()[
                "result"
            ]
            assert out == {"cancelled": jid}
            jobs = client.post("/api/graph/capabilities/list_index_jobs", json={}).json()["result"]
            later = next(j for j in jobs if j["id"] == jid)
            assert later["status"] == "cancelled"

    def test_agent_bridge_reaches_graph_tools(self, tmp_path) -> None:
        """Domain capabilities reach the agent tool set via the bridge (a
        precondition for graph explanation and graph building)."""
        app = build(tmp_path / "data3", tmp_path / "ws3")
        backend = app.state.backend
        names = backend.agent.spawner._toolbelt.names()
        for expect in (
            "graph__enqueue_index",
            "graph__query_graph",
            "graph__set_node",
            "graph__set_relationship",
            "graph__get_subgraph",
        ):
            assert expect in names
        # Graph tools survive the Atlas capability trim (the enqueue-before-index
        # discipline); the allowlist grants by the graph__* prefix and must expand
        # to these concrete tools
        from agent.personas import PERSONAS

        allow = PERSONAS["graph_guide"].tool_allow or ()
        assert "graph__*" in allow
        trimmed_names = set(backend.agent.spawner._toolbelt.trimmed(allow).names())
        assert {"graph__enqueue_index", "graph__graph_guide"} <= trimmed_names


class TestL0ViaProvider:
    def test_l0_provider_through_list_sources(self, tmp_path) -> None:
        """The assembly root's resource catalog provider fetches data through the
        list_sources capability (the composition root never reads STORES directly); two documents
        sharing a tag enter L0 and produce a RELATED edge."""
        app = build(
            tmp_path / "data",
            tmp_path / "ws",
            wire_extras={"sources": {"parse_fn": lambda path, ext: []}},
        )
        with TestClient(app) as client:
            src = tmp_path / "ws" / "imports"
            src.mkdir(parents=True, exist_ok=True)
            for i, title in enumerate(("Manual A", "Manual B")):
                f = src / f"a{i}.md"
                f.write_text("body content", encoding="utf-8")
                ref = client.post(
                    "/api/sources/capabilities/add_document",
                    json={"file_path": str(f), "title": title, "tags": ["shared-tag"]},
                )
                assert ref.status_code == 202
            # Wait until both documents are ready (L0 excludes importing/parsing/failed)
            stats = {}
            deadline = time.time() + 8
            while time.time() < deadline:
                stats = client.post("/api/sources/capabilities/sources_stats", json={}).json()[
                    "result"
                ]
                if (
                    stats.get("doc") == 2
                    and not stats.get("importing")
                    and not stats.get("parsing")
                ):
                    break
                time.sleep(0.1)
            else:
                raise AssertionError(f"documents not ready: {stats}")

            ref = client.post("/api/graph/capabilities/enqueue_l0", json={"kinds": ["doc"]})
            assert ref.status_code == 202
            job = _wait_job_done(client, ref.json()["job"]["job_id"])
            assert job["status"] == "done", job["error"]

            view = client.post("/api/graph/capabilities/l0_view", json={"kinds": ["doc"]}).json()[
                "result"
            ]
            assert len(view["nodes"]) == 2  # the provider is not an empty callback
            assert view["edges"] and view["edges"][0]["type"] == "RELATED"
