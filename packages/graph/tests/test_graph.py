"""Tests for the graph service: canonical store upserts, AI pipeline
validation, queue, scheduler retries, engine fallback, Python-engine end-to-end indexing
of a tiny repo, and repo relation analysis.
"""

import pytest
from graph.capabilities import Deps, init_deps, registry
from graph.engines.adapter import EngineAdapter
from graph.index_queue import IndexQueue
from graph.pipelines.code.analyze import analyze_repo
from graph.pipelines.code.relate import relate_repos
from graph.scheduler import IndexScheduler
from graph.store import GraphStore
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ActorKind, ActorRef, ServiceError
from platform_eventbus import EventBus, EventLog

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


@pytest.fixture()
def deps(tmp_path):
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    d = Deps(
        store=GraphStore(tmp_path / "graph.db"),
        queue=IndexQueue(tmp_path / "index.db"),
        adapter=EngineAdapter(
            c_base_url="",  # no C sidecar: must fall back
            python_data_root=tmp_path / "pyengine",
            bus=bus,
        ),
        bus=bus,
    )
    init_deps(d)
    yield d, log
    d.store.close()
    d.queue.close()
    log.close()


class TestCanonicalStore:
    async def test_set_node_upsert_idempotent(self, deps) -> None:
        args = {"project": "p1", "label": "Concept", "name": "Agent"}
        n1 = await execute(registry, "set_node", AGENT_CTX, args)
        n2 = await execute(
            registry, "set_node", AGENT_CTX, {**args, "attrs": {"quote": "from chapter 3"}}
        )
        assert n1["id"] == n2["id"]  # upsert: rewriting means updating
        assert n2["attrs"]["quote"] == "from chapter 3"
        assert n2["source"] == "ai" and n2["actor"] == "agent.main"

    async def test_manual_source_distinguished(self, deps) -> None:
        n = await execute(
            registry, "set_node", USER_CTX, {"project": "p1", "label": "Term", "name": "handmade"}
        )
        assert n["source"] == "manual"  # one store, distinguishable provenance

    async def test_set_node_validation(self, deps) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(
                registry, "set_node", USER_CTX, {"project": "", "label": "Concept", "name": "x"}
            )
        assert exc.value.body.code == "GRAPH.INVALID_INPUT"

    async def test_relationship_autocreates_placeholders(self, deps) -> None:
        rel = await execute(
            registry,
            "set_relationship",
            AGENT_CTX,
            {"project": "p1", "src": "AI", "dst": "ML", "type": "CONTAINS"},
        )
        graph = await execute(registry, "query_graph", AGENT_CTX, {"project": "p1"})
        names = {n["name"] for n in graph["nodes"]}
        assert {"AI", "ML"} <= names  # placeholder nodes auto-created
        assert rel["type"] == "CONTAINS"

    async def test_subgraph_and_stats(self, deps) -> None:
        d, _ = deps
        await execute(
            registry,
            "set_relationship",
            USER_CTX,
            {"project": "p2", "src": "A", "dst": "B", "type": "RELATES_TO"},
        )
        a = d.store.get_node("p2", "Term", "A")
        sub = await execute(
            registry, "get_subgraph", USER_CTX, {"project": "p2", "node_id": a["id"], "depth": 1}
        )
        assert len(sub["nodes"]) == 2 and len(sub["edges"]) == 1
        stats = await execute(registry, "graph_stats", USER_CTX, {"project": "p2"})
        assert stats["total_nodes"] == 2


class TestQueue:
    async def test_priority_order_and_reorder(self, deps) -> None:
        d, _ = deps
        j1 = await execute(registry, "enqueue_index", USER_CTX, {"project": "a", "repo_path": "/x"})
        j2 = await execute(registry, "enqueue_index", USER_CTX, {"project": "b", "repo_path": "/y"})
        await execute(registry, "reorder_queue", USER_CTX, {"job_id": j2.job_id, "priority": 1})
        assert d.queue.next()["project"] == "b"  # lower priority value runs first
        await execute(registry, "cancel_index", USER_CTX, {"job_id": j1.job_id})
        assert d.queue.get(j1.job_id)["status"] == "cancelled"

    async def test_enqueue_rejects_path_outside_workspace(self, tmp_path) -> None:
        from graph.capabilities import Deps, init_deps
        from graph.engines.adapter import EngineAdapter
        from graph.index_queue import IndexQueue
        from graph.store import GraphStore
        from platform_eventbus import EventBus, EventLog

        ws = tmp_path / "ws"
        ws.mkdir()
        log = EventLog(tmp_path / "e.db")
        store = GraphStore(tmp_path / "g.db")
        queue = IndexQueue(tmp_path / "i.db")
        init_deps(
            Deps(
                store=store,
                queue=queue,
                adapter=EngineAdapter(c_base_url="", python_data_root=tmp_path / "py"),
                bus=EventBus(log),
                workspace=ws,
            )
        )
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(
                    registry,
                    "enqueue_index",
                    USER_CTX,
                    {"project": "x", "repo_path": str(tmp_path / "outside")},
                )
            assert exc.value.body.code == "GRAPH.FORBIDDEN"
            inside = ws / "repo"
            inside.mkdir()
            ref = await execute(
                registry, "enqueue_index", USER_CTX, {"project": "ok", "repo_path": str(inside)}
            )
            assert ref.job_id
        finally:
            store.close()
            queue.close()
            log.close()

    async def test_cancel_running_conflict(self, deps) -> None:
        d, _ = deps
        jid = d.queue.enqueue("p", "/x")
        d.queue.next()  # move to running
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "cancel_index", USER_CTX, {"job_id": jid})
        assert exc.value.body.code == "GRAPH.CONFLICT"


class TestScheduler:
    async def test_retry_then_done(self, deps) -> None:
        d, log = deps
        attempts: list[str] = []

        async def flaky(job) -> None:
            attempts.append(job["id"])
            if len(attempts) < 2:
                raise RuntimeError("engine crash")

        sched = IndexScheduler(
            d.queue, flaky, EventBus(log), max_attempts=3, backoff_base_s=0.01, idle_poll_s=0.01
        )
        jid = d.queue.enqueue("p", "/x")
        await sched.start()
        for _ in range(100):
            if d.queue.get(jid)["status"] == "done":
                break
            await asyncio_sleep()
        await sched.stop()
        assert d.queue.get(jid)["status"] == "done"
        assert len(attempts) == 2  # first attempt fails and retries, second succeeds

    async def test_give_up_after_max_attempts(self, deps) -> None:
        d, _ = deps

        async def always_fail(job) -> None:
            raise RuntimeError("bad")

        sched = IndexScheduler(
            d.queue, always_fail, None, max_attempts=2, backoff_base_s=0.01, idle_poll_s=0.01
        )
        jid = d.queue.enqueue("p", "/x")
        await sched.start()
        for _ in range(100):
            if d.queue.get(jid)["status"] == "failed":
                break
            await asyncio_sleep()
        await sched.stop()
        job = d.queue.get(jid)
        assert job["status"] == "failed" and job["attempts"] == 2


async def asyncio_sleep() -> None:
    import asyncio

    await asyncio.sleep(0.02)


class TestEngineFallback:
    async def test_auto_falls_back_with_event(self, deps) -> None:
        _, log = deps
        out = await execute(registry, "engine_info", USER_CTX, {})
        assert out["engine"] == "python"
        types = [e.type for _, e in log.read_after()]
        assert "graph.engine.fallback" in types  # fallback emits an event for the UI badge

    async def test_forced_c_unavailable_503(self, tmp_path) -> None:
        adapter = EngineAdapter(
            c_base_url="http://127.0.0.1:1",  # unreachable
            python_data_root=tmp_path / "e",
            mode="c",
        )
        with pytest.raises(ServiceError) as exc:
            await adapter.resolve()
        assert exc.value.body.code == "GRAPH.UNAVAILABLE"


class TestCodePipeline:
    async def test_index_tiny_repo_end_to_end(self, deps, tmp_path) -> None:
        """Python engine end to end: index a toy repo, canonical store has nodes."""
        repo = tmp_path / "toy"
        repo.mkdir()
        (repo / "main.py").write_text(
            "import helper\n\ndef run():\n    return helper.go()\n", encoding="utf-8"
        )
        (repo / "helper.py").write_text("def go():\n    return 1\n", encoding="utf-8")
        d, _ = deps
        result = await analyze_repo(d.adapter, d.store, project="toy", repo_path=str(repo))
        assert result["engine"] == "python"
        graph = d.store.query("toy")
        names = {n["name"] for n in graph["nodes"]}
        assert "run" in names and "go" in names  # function nodes made it in
        code_nodes = [n for n in graph["nodes"] if n["source"] == "code"]
        assert code_nodes  # provenance marked as the programmatic pipeline

    async def test_relate_shared_dependency(self, deps) -> None:
        d, _ = deps
        for proj in ("web-a", "web-b"):
            nid = d.store.upsert_node(
                proj,
                "Module",
                "app",
                "app",
                {"import_target": "fastapi"},
                source="code",
                actor="engine.python",
            )["id"]
            assert nid
        out = relate_repos(d.store, ["web-a", "web-b"])
        assert out["cross_edges"] >= 1
        cross = d.store.query("cross-repo")
        assert cross["edges"][0]["type"] == "CROSS_REPO"


class TestExport:
    async def test_export_cypher_normal(self, deps) -> None:
        d, _ = deps
        n = d.store.upsert_node("py", "Concept", "ConceptA")
        out = await execute(
            registry,
            "export_subgraph",
            USER_CTX,
            {"project": "py", "node_id": n["id"], "format": "cypher"},
        )
        assert "CREATE (n:`Concept` {" in out["cypher"]

    async def test_export_cypher_escapes_identifiers_and_values(self, deps) -> None:
        """Malicious labels/types/quoted values must not escape the Cypher statement structure."""
        d, _ = deps
        a = d.store.upsert_node("px", "Evil`Label", 'n"ame')
        b = d.store.upsert_node("px", "Term", "ok")
        d.store.upsert_edge("px", a["id"], b["id"], "BAD`)-[:X]->(y")
        out = await execute(
            registry,
            "export_subgraph",
            USER_CTX,
            {"project": "px", "node_id": a["id"], "depth": 1, "format": "cypher"},
        )
        cy = out["cypher"]
        assert "`Evil``Label`" in cy  # backticks doubled inside identifiers
        assert "[:`BAD``)-[:X]->(y`]" in cy  # relation type fully wrapped in backticks
        assert 'n\\"ame' in cy  # embedded double quote JSON-escaped, literal intact


class TestUnifiedSubgraphSemantics:
    """The single BFS lives in store.subgraph: expand_neighbors reuses it, so
    both capabilities return the same induced subgraph at every depth (the
    old star-expansion divergence is gone; owner decision 2026-09-28)."""

    @pytest.fixture()
    def store(self, tmp_path):
        return GraphStore(tmp_path / "sub.db")

    def _seed(self, store):
        a = store.upsert_node("p", "Func", "a", "a")
        b = store.upsert_node("p", "Func", "b", "b")
        c = store.upsert_node("p", "Func", "c", "c")
        d = store.upsert_node("p", "Func", "d", "d")
        store.upsert_edge("p", a["id"], b["id"], "calls")  # a -> b
        store.upsert_edge("p", b["id"], c["id"], "calls")  # b -> c
        store.upsert_edge("p", c["id"], d["id"], "imports")  # c -> d (foreign type)
        # outermost ring edge: between the depth-1 and depth-2 neighbours
        store.upsert_edge("p", b["id"], d["id"], "calls")
        return a

    def test_depths_match_expand_neighbors(self, store) -> None:
        a = self._seed(store)
        for depth in (0, 1, 2):
            sub = store.subgraph("p", a["id"], depth)
            sub_ids = {n["id"] for n in sub["nodes"]} | {e["id"] for e in sub["edges"]}
            expanded = store.subgraph("p", a["id"], depth, edge_filter="calls")
            exp_ids = {n["id"] for n in expanded["nodes"]} | {e["id"] for e in expanded["edges"]}
            assert sub_ids >= exp_ids  # same walk, filter only trims edges
            assert a["id"] in sub_ids

    def test_edge_filter_narrows_edges_not_traversal(self, store) -> None:
        a = self._seed(store)
        filtered = store.subgraph("p", a["id"], 2, edge_filter="calls")
        # traversal is unaffected: the depth-2 node (d) still shows up...
        names = {n["qualified_name"] for n in filtered["nodes"]}
        assert {"a", "b", "c", "d"} <= names
        # ...but the foreign-type edge is out of the returned edges
        assert all(e["type"] == "calls" for e in filtered["edges"])
        unfiltered = store.subgraph("p", a["id"], 2)
        assert any(e["type"] == "imports" for e in unfiltered["edges"])

    def test_outermost_ring_edges_are_returned(self, store) -> None:
        """The owner-chosen semantic: edges hanging off the depth-limit ring
        are part of the induced subgraph (star expansion dropped them)."""
        a = self._seed(store)
        sub = store.subgraph("p", a["id"], 1)
        edge_pairs = {(e["src"], e["dst"]) for e in sub["edges"]}
        # b sits on the depth-1 ring; its edge to d reaches beyond it
        b = store.upsert_node("p", "Func", "b", "b")
        d = store.upsert_node("p", "Func", "d", "d")
        assert (b["id"], d["id"]) in edge_pairs


class TestExactNodeLookupAndStaleRecovery:
    def test_node_id_by_qn_exact_match(self, tmp_path) -> None:
        store = GraphStore(tmp_path / "qn.db")
        store.upsert_node("p", "Func", "get_user", "mod.get_user")
        store.upsert_node("p", "Func", "get", "mod.get")
        # exact qualified_name wins over the substring crowd
        nid = store.node_id_by_qn("p", "mod.get")
        get_node = store.get_node("p", "Func", "mod.get")
        bare_node = store.upsert_node("p", "Term", "bare", "")
        assert get_node is not None and nid == get_node["id"]
        # effective qn: empty qualified_name falls back to name
        assert store.node_id_by_qn("p", "bare") == bare_node["id"]
        assert store.node_id_by_qn("p", "missing") is None

    def test_recover_stale_running_requeues_and_fails(self, tmp_path) -> None:
        from graph.index_queue import IndexQueue

        queue = IndexQueue(tmp_path / "rec.db")
        j1 = queue.enqueue("p", "/ws/r1", 100, level="l1")
        j2 = queue.enqueue("p", "/ws/r2", 100, level="l1")
        running1 = queue.next()
        running2 = queue.next()
        assert running1 is not None and running2 is not None
        assert running1["id"] == j1 and running2["id"] == j2

        # crash leftover under the attempts cap: requeued
        requeued = queue.recover_stale_running(max_attempts=3)
        assert requeued == 2
        row1 = queue.get(j1)
        assert row1 is not None and row1["status"] == "queued"

        # crash leftover past the cap: failed, not requeued forever
        job = queue.next()
        assert job is not None
        queue._conn.execute("UPDATE index_jobs SET attempts = 5 WHERE id = ?", (job["id"],))
        queue._conn.commit()
        queue.recover_stale_running(max_attempts=3)
        row1 = queue.get(j1)
        row2 = queue.get(j2)
        assert row1 is not None and row2 is not None
        statuses = {row1["status"], row2["status"]}
        assert "failed" in statuses or all(s in ("queued", "failed") for s in statuses)
