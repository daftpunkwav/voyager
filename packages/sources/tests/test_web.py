"""Web submodule tests: the full save_url path (mocked httpx), SSRF guards
(resolve-and-pin), manual entry, metadata, removal events.

Fully offline: an injected resolver fake stands in for DNS.
"""

import httpx
import pytest
import sources.modules.web.capabilities as web_caps
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ActorKind, ActorRef, ServiceError
from sources.capabilities import SourcesDeps, init_all, registry
from sources.modules.web.store import WebStore

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))

_PUBLIC_IP = "93.184.216.34"  # fake public IP for tests (no real network)


@pytest.fixture()
def deps(tmp_path):
    import asyncio

    from platform_eventbus import EventBus, EventLog
    from platform_secrets import SecretStore
    from sources.modules.doc.store import DocStore
    from sources.modules.repo.store import RepoStore

    log = EventLog(tmp_path / "events.db")
    d = SourcesDeps(
        repo_store=RepoStore(tmp_path / "repo.db"),
        doc_store=DocStore(tmp_path / "doc.db"),
        web_store=WebStore(tmp_path / "web.db"),
        secrets=SecretStore(tmp_path / "secrets.db", key_material="t"),
        bus=EventBus(log),
        repo_queue=asyncio.Queue(),
        doc_queue=asyncio.Queue(),
        workspace=tmp_path / "ws",
    )
    init_all(d)
    yield d, log
    d.repo_store.close()
    d.doc_store.close()
    d.web_store.close()
    log.close()


@pytest.fixture()
def web_env(deps, tmp_path, monkeypatch):
    """Injected resolver + MockTransport client; returns (deps, log, calls)."""
    d, log = deps
    calls: list[httpx.Request] = []

    async def resolve(host: str, port: int) -> list[str]:
        if host == "example.com":
            return [_PUBLIC_IP]
        raise OSError(f"test resolver unknown host: {host}")

    web_caps.init_deps(web_caps.WebDeps(store=d.web_store, bus=d.bus, resolve=resolve))
    orig = httpx.AsyncClient

    def recording_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text="<title>Test Page</title><p>First paragraph body</p>")

    def factory(**kw):
        kw.pop("follow_redirects", None)
        return orig(transport=httpx.MockTransport(recording_handler), follow_redirects=False, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return d, log, calls


class TestSaveUrl:
    async def test_saves_page_with_extracted_content(self, web_env) -> None:
        _, log, _ = web_env
        page = await execute(
            registry,
            "save_url",
            USER_CTX,
            {"url": "https://example.com/post/1", "tags": ["tutorial"]},
        )
        assert page["title"] == "Test Page"
        assert "First paragraph body" in page["content"]
        assert page["domain"] == "example.com"
        assert page["tags"] == ["tutorial"]
        types = [e.type for _, e in log.read_after()]
        assert "source.added" in types and "source.ready" in types

    async def test_pinned_ip_with_original_host(self, web_env) -> None:
        """The connection targets the validated IP while the Host header keeps
        the original hostname (routing/SNI semantics preserved).
        """
        _, _, calls = web_env
        await execute(registry, "save_url", USER_CTX, {"url": "https://example.com/x"})
        assert calls and calls[0].url.host == _PUBLIC_IP
        assert calls[0].headers.get("host") == "example.com"

    async def test_huge_body_is_read_under_the_byte_cap(self, web_env) -> None:
        """A multi-megabyte page is bounded at read time: the stored content
        stays far below the offered body instead of buffering it all."""
        import sources.modules.web.capabilities as wc

        _, _, _ = web_env
        page = await execute(registry, "save_url", USER_CTX, {"url": "https://example.com/huge"})
        # 6 MB offered; the byte cap bounds the buffered body (and therefore
        # the stored content) instead of the read swallowing it whole.
        assert len(page["content"]) < wc._MAX_BODY_BYTES

    async def test_ssrf_guards(self, deps) -> None:
        """Loopback/link-local/non-http schemes are rejected before any
        request goes out.
        """
        with pytest.raises(ServiceError, match="not in public address space"):
            await execute(registry, "save_url", USER_CTX, {"url": "http://127.0.0.1:8123/api"})
        with pytest.raises(ServiceError, match="not in public address space"):
            await execute(
                registry, "save_url", USER_CTX, {"url": "http://169.254.169.254/latest/meta-data"}
            )
        with pytest.raises(ServiceError, match="http/https"):
            await execute(registry, "save_url", USER_CTX, {"url": "file:///etc/passwd"})

    async def test_resolved_loopback_rejected(self, deps) -> None:
        """Hosts resolving to loopback/IPv4-mapped loopback must be rejected;
        checking literals alone is not enough.
        """
        d, _ = deps

        async def resolve_loopback(host: str, port: int) -> list[str]:
            if host == "localtest.me":
                return ["127.0.0.1"]
            if host == "mapped.example":
                return ["::ffff:127.0.0.1"]
            raise OSError(host)

        web_caps.init_deps(web_caps.WebDeps(store=d.web_store, bus=d.bus, resolve=resolve_loopback))
        with pytest.raises(ServiceError, match="not in public address space"):
            await execute(registry, "save_url", USER_CTX, {"url": "http://localtest.me/"})
        with pytest.raises(ServiceError, match="not in public address space"):
            await execute(registry, "save_url", USER_CTX, {"url": "http://mapped.example/"})


class TestPages:
    async def test_add_list_get_remove_event(self, web_env) -> None:
        _, log, _ = web_env
        page = await execute(
            registry,
            "add_page",
            USER_CTX,
            {
                "title": "manual clipping",
                "content": "body text" * 300,
                "url": "https://example.com/a",
            },
        )
        assert page["summary"]
        pages = await execute(registry, "list_pages", USER_CTX, {"query": "manual"})
        assert len(pages) == 1
        full = await execute(registry, "get_page", AGENT_CTX, {"page_id": page["id"]})
        assert len(full["content"]) > len(full["summary"])
        await execute(registry, "remove_page", USER_CTX, {"page_id": page["id"]})
        assert await execute(registry, "list_pages", USER_CTX, {}) == []
        types = [e.type for _, e in log.read_after(types=["source.removed"])]
        assert types == ["source.removed"]

    async def test_set_meta_and_validation(self, web_env) -> None:
        page = await execute(registry, "add_page", USER_CTX, {"title": "old title", "content": "x"})
        updated = await execute(
            registry,
            "set_page_meta",
            USER_CTX,
            {"page_id": page["id"], "title": "new title", "tags": ["ai"]},
        )
        assert updated["title"] == "new title" and updated["tags"] == ["ai"]
        with pytest.raises(ServiceError, match="Invalid tag"):
            await execute(
                registry, "set_page_meta", USER_CTX, {"page_id": page["id"], "tags": ['q"q']}
            )
        with pytest.raises(ServiceError, match="not found"):
            await execute(registry, "get_page", USER_CTX, {"page_id": "ghost"})
