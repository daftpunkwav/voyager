"""Sources service tests: repo import/sort/metadata/secret boundaries and the
aggregate registry.

Doc/web submodule cases live in test_doc.py / test_web.py; the unified
cross-kind stream in test_aggregate.py. GitHub API and git clone are
always mocked -- tests never touch the network or git.
"""

import asyncio
from pathlib import Path

import httpx
import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ActorKind, ActorRef
from platform_eventbus import EventBus, EventLog
from platform_secrets import SecretStore
from sources.capabilities import SourcesDeps, init_all, registry
from sources.modules.doc.store import DocStore
from sources.modules.repo import github as github_mod
from sources.modules.repo.store import RepoStore
from sources.modules.web.store import WebStore

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


def _mock_github(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/readme"):
            import base64

            return httpx.Response(
                200,
                json={
                    "encoding": "base64",
                    "content": base64.b64encode(b"# hello README").decode(),
                },
            )
        if "/search/" in path:
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "name": "langgraph",
                            "html_url": "https://github.com/langchain-ai/langgraph",
                            "owner": {"login": "langchain-ai"},
                            "description": "orchestration",
                            "stargazers_count": 100,
                            "language": "Python",
                        }
                    ]
                },
            )
        if path.endswith("/starred"):
            return httpx.Response(
                200,
                json=[
                    {
                        "name": "langgraph",
                        "html_url": "https://github.com/langchain-ai/langgraph",
                        "owner": {"login": "langchain-ai"},
                        "description": "starred repos",
                        "stargazers_count": 100,
                        "language": "Python",
                    }
                ],
            )
        return httpx.Response(
            200,
            json={
                "name": path.rsplit("/", 1)[-1],
                "html_url": f"https://github.com{path}",
                "description": "test repo",
                "stargazers_count": 42,
                "language": "Python",
            },
        )

    orig = httpx.AsyncClient
    monkeypatch.setattr(
        github_mod.httpx,
        "AsyncClient",
        lambda **kw: orig(transport=httpx.MockTransport(handler), **kw),
    )


@pytest.fixture()
def deps(tmp_path, monkeypatch):
    _mock_github(monkeypatch)
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    repo_queue: asyncio.Queue = asyncio.Queue()
    doc_queue: asyncio.Queue = asyncio.Queue()
    d = SourcesDeps(
        repo_store=RepoStore(tmp_path / "repo.db"),
        doc_store=DocStore(tmp_path / "doc.db"),
        web_store=WebStore(tmp_path / "web.db"),
        secrets=SecretStore(tmp_path / "secrets.db", key_material="t"),
        bus=bus,
        repo_queue=repo_queue,
        doc_queue=doc_queue,
        workspace=tmp_path / "ws",
    )
    init_all(d)
    yield d, log
    d.repo_store.close()
    d.doc_store.close()
    d.web_store.close()
    log.close()


class TestRepo:
    async def test_import_registers_and_enqueues(self, deps) -> None:
        d, log = deps
        ref = await execute(
            registry, "import_repo", USER_CTX, {"url": "https://github.com/langchain-ai/langgraph"}
        )
        repo = d.repo_store.get(ref.job_id)
        assert repo["status"] == "importing"
        assert repo["readme"].startswith("# hello")  # README cached at import time
        assert repo["stars"] == 42
        assert d.repo_queue.qsize() == 1  # enqueued for cloning
        events = [e.type for _, e in log.read_after()]
        assert "source.added" in events

    async def test_duplicate_conflict(self, deps) -> None:
        d, _ = deps
        d.repo_store.add({"name": "a", "url": "https://github.com/o/a", "status": "ready"})
        with pytest.raises(Exception, match="already imported"):
            await execute(registry, "import_repo", USER_CTX, {"url": "https://github.com/o/a"})

    async def test_reimport_preserves_user_meta(self, deps) -> None:
        """Re-import over a conflicting URL updates source fields only;
        category/tags/progress/note are preserved and the id stays the same.
        """
        d, _ = deps
        rid1 = d.repo_store.add(
            {
                "name": "a",
                "owner": "o",
                "url": "https://github.com/o/a",
                "status": "failed",
                "readme": "old",
            }
        )
        d.repo_store.set_meta(rid1, category="study", tags=["x"], progress="done", note="my note")
        rid2 = d.repo_store.add(
            {
                "name": "a",
                "owner": "o",
                "url": "https://github.com/o/a",
                "status": "importing",
                "readme": "new",
                "stars": 99,
            }
        )
        assert rid2 == rid1  # the surviving row's id is returned on conflict
        repo = d.repo_store.get(rid1)
        assert repo["category"] == "study" and repo["tags"] == ["x"]
        assert repo["note"] == "my note" and repo["readme"] == "new"
        assert repo["stars"] == 99 and repo["status"] == "importing"

    async def test_sort_by_name_and_summary_hides_readme(self, deps) -> None:
        d, _ = deps
        for name in ("beta", "alpha", "gamma"):
            d.repo_store.add(
                {
                    "name": name,
                    "url": f"https://github.com/o/{name}",
                    "status": "ready",
                    "readme": "long readme",
                }
            )
        out = await execute(registry, "sort_repos", AGENT_CTX, {"by": "name"})
        assert [r["name"] for r in out] == ["alpha", "beta", "gamma"]  # agents sort equally
        assert "readme" not in out[0]  # list summaries carry no body text
        full = await execute(registry, "get_readme", AGENT_CTX, {"repo_id": out[0]["id"]})
        assert full["readme"] == "long readme"

    async def test_meta_and_categories(self, deps) -> None:
        d, _ = deps
        rid = d.repo_store.add({"name": "a", "url": "https://github.com/o/a"})
        await execute(
            registry,
            "set_repo_meta",
            USER_CTX,
            {
                "repo_id": rid,
                "category": "Agent frameworks",
                "tags": ["py", "graph"],
                "progress": "learning",
            },
        )
        assert await execute(registry, "list_categories", USER_CTX, {}) == ["Agent frameworks"]
        repo = d.repo_store.get(rid)
        assert repo["tags"] == ["py", "graph"] and repo["progress"] == "learning"

    async def test_remove_repo(self, deps) -> None:
        d, _ = deps
        rid = d.repo_store.add({"name": "a", "url": "https://github.com/o/a"})
        await execute(registry, "remove_repo", USER_CTX, {"repo_id": rid})
        assert d.repo_store.get(rid) is None

    async def test_search_remote(self, deps) -> None:
        out = await execute(registry, "search_remote_repos", AGENT_CTX, {"query": "langgraph"})
        assert out[0]["name"] == "langgraph"

    async def test_list_starred(self, deps) -> None:
        """The real endpoint is /users/{u}/starred."""
        out = await execute(registry, "list_starred_repos", USER_CTX, {"username": "someone"})
        assert out[0]["owner"] == "langchain-ai" and out[0]["stars"] == 100

    async def test_github_token_user_only(self, deps) -> None:
        from platform_contracts import ServiceError

        with pytest.raises(ServiceError) as exc:
            await execute(registry, "set_github_token", AGENT_CTX, {"token": "t"})
        assert exc.value.body.code == "SOURCES.FORBIDDEN"

    def test_parse_repo_url_rejects_bad_charset(self) -> None:
        """Owner/repo feed the clone destination and API paths; a crafted
        name (path separators, dot segments, etc.) is rejected up front."""
        from platform_contracts import ServiceError

        assert github_mod.parse_repo_url("https://github.com/langchain-ai/langgraph") == (
            "langchain-ai",
            "langgraph",
        )
        assert github_mod.parse_repo_url("https://github.com/owner/repo.git") == ("owner", "repo")
        for bad in (
            "https://github.com/..%2f/x",
            "https://github.com/a/b+c",
            "https://github.com/a b/c",
            "https://github.com/../x",
            "https://github.com/./x",
            # a trailing newline must not slip past the charset check
            # (match+$ matches before a final \n; fullmatch does not);
            # urlparse would silently strip it and rewrite the target repo
            "https://github.com/abc\n/def",
        ):
            with pytest.raises(ServiceError, match="Invalid GitHub owner/repo"):
                github_mod.parse_repo_url(bad)

    def test_parse_repo_url_rejects_non_github_hosts(self) -> None:
        """Hostname (not substring) validation: lookalike domains and URLs
        where 'github.com' is not followed by '/' must be a clean 400, never
        an unhandled IndexError from split()[1]."""
        from platform_contracts import ServiceError

        for bad in (
            "https://github.com.evil.com/a/b",
            "https://evilgithub.com/a/b",
            "https://notgithub.com/a/b",
            "ftp://github.com/a/b",
            "github.com/a/b",
        ):
            with pytest.raises(ServiceError, match="Only GitHub repo URLs"):
                github_mod.parse_repo_url(bad)


class TestRepoWorker:
    async def test_clone_then_ready(self, deps, tmp_path) -> None:
        d, log = deps
        rid = d.repo_store.add({"owner": "o", "name": "r", "url": "https://github.com/o/r"})

        async def fake_clone(owner: str, name: str, dest: Path) -> None:
            dest.mkdir(parents=True)
            (dest / "README.md").write_text("ok", encoding="utf-8")

        worker = RepoWorker(
            d.repo_store, EventBus(log), d.repo_queue, tmp_path / "ws", clone_fn=fake_clone
        )
        await worker.start()
        d.repo_queue.put_nowait(rid)
        # Poll for the terminal event, not a fixed sleep: stop() cancels the
        # worker, and source.ready is emitted after the status flip.
        for _ in range(200):
            await asyncio.sleep(0.02)
            if log.read_after(types=["source.ready"]):
                break
        await worker.stop()
        repo = d.repo_store.get(rid)
        assert repo["status"] == "ready" and "o__r" in repo["local_path"]
        types = [e.type for _, e in log.read_after(types=["source.ready", "task.failed"])]
        assert types == ["source.ready"]  # agents pick up from this event via observe

    async def test_clone_failure_marks_failed(self, deps, tmp_path) -> None:
        d, _log = deps
        rid = d.repo_store.add({"owner": "o", "name": "bad", "url": "https://github.com/o/bad"})

        async def boom(owner, name, dest) -> None:
            raise RuntimeError("network unreachable")

        worker = RepoWorker(d.repo_store, None, d.repo_queue, tmp_path / "ws", clone_fn=boom)
        await worker.start()
        d.repo_queue.put_nowait(rid)
        # Poll until the worker persisted the failure (fixed sleeps race a
        # loaded session; stop() would cancel mid-job).
        for _ in range(200):
            await asyncio.sleep(0.02)
            if d.repo_store.get(rid)["status"] == "failed":
                break
        await worker.stop()
        assert d.repo_store.get(rid)["status"] == "failed"


# RepoWorker imported from its own module (keeps the import surface stable)
from sources.modules.repo.worker import RepoWorker


class TestAggregateRegistry:
    def test_registry_merges_all_modules(self) -> None:
        names = registry.names()
        assert {"import_repo", "add_document", "save_url", "list_sources"} <= set(names)
        assert len(names) == len(set(names))  # no duplicate capability names

    def test_service_json_matches_registry(self) -> None:
        """The service.json capability list matches the registry (single
        source of truth).
        """
        import json

        card = json.loads((Path(__file__).resolve().parents[1] / "service.json").read_text("utf-8"))
        assert set(card["capabilities"]) == set(registry.names())


class TestReadOnlyMetadata:
    def test_read_capabilities_declared_non_write(self) -> None:
        """Read-only lookups must declare write=False: a readonly subagent
        dispatch runs trimmed_read_only(), which drops every write tool by
        construction — an undeclared read (the write=True default) would
        vanish from the dispatched surface (explainer/Elio regression)."""
        expected = {
            # repo
            "list_repos",
            "sort_repos",
            "get_readme",
            "get_repo",
            "list_categories",
            "search_remote_repos",
            "list_starred_repos",
            # doc
            "list_documents",
            "get_document",
            "get_doc_section",
            "search_documents",
            # web
            "list_pages",
            "get_page",
        }
        registered = set(registry.names())
        assert expected <= registered
        for name in sorted(expected):
            assert registry.get(name).write is False, name

    def test_mutation_capabilities_stay_write(self) -> None:
        """The write side keeps the default (or explicit) write=True: a
        readonly dispatch must still lose these."""
        for name in (
            "import_repo",
            "set_repo_meta",
            "remove_repo",
            "add_document",
            "set_document_meta",
            "remove_document",
            "save_url",
            "add_page",
            "set_page_meta",
            "remove_page",
            "set_github_token",
        ):
            assert registry.get(name).write is True, name
