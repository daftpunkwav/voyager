"""Tests for web_search (DuckDuckGo backend).

MockTransport throughout; the tests never touch the network (DNS failures are treated as
allow, semantics unchanged). The parser is additionally tested as a pure function,
covering uddg redirect-shell unwrapping and tag stripping.
"""

import agent.tools.net.web_search as web_mod
import httpx
from agent.policy import NetworkPolicy, PolicyEngine

#: A minimal sample of the endpoint's current shape (2 results: a redirect-shell link plus inline <b> tags)
_DDG_PAGE = """
<div class="result">
  <a rel="nofollow" class="result__a"
     href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&amp;rut=abc">
     Result <b>One</b></a>
  <a class="result__snippet" href="#">first <b>snippet</b> text</a>
</div>
<div class="result">
  <a rel="nofollow" class="result__a" href="https://direct.example.com/b">Result Two</a>
  <a class="result__snippet" href="#">second snippet</a>
</div>
"""


def _client_factory(handler):
    orig = httpx.AsyncClient

    def factory(**kw):
        kw.pop("follow_redirects", None)
        return orig(transport=httpx.MockTransport(handler), follow_redirects=False, **kw)

    return factory


def _search(monkeypatch, handler, domains=("duckduckgo.com",)):
    monkeypatch.setattr(web_mod.httpx, "AsyncClient", _client_factory(handler))
    policy = PolicyEngine(network=NetworkPolicy(mode="whitelist", domains=domains))
    return web_mod.web_search_tool(policy).handler


class TestParse:
    def test_parse_results_unwrap_and_strip(self) -> None:
        out = web_mod._parse_ddg_results(_DDG_PAGE, limit=8)
        assert [r["title"] for r in out] == ["Result One", "Result Two"]
        assert out[0]["url"] == "https://example.com/a"  # the uddg redirect shell is unwrapped
        assert out[1]["url"] == "https://direct.example.com/b"  # direct links pass through verbatim
        assert out[0]["snippet"] == "first snippet text"

    def test_parse_shape_change_returns_empty(self) -> None:
        assert web_mod._parse_ddg_results("<html>captcha</html>", 8) == []

    def test_limit(self) -> None:
        page = _DDG_PAGE * 5
        assert len(web_mod._parse_ddg_results(page, 3)) == 3


class TestHandler:
    async def test_happy_path_posts_query(self, monkeypatch) -> None:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["body"] = request.content.decode("utf-8")
            seen["ua"] = request.headers.get("user-agent", "")
            return httpx.Response(200, text=_DDG_PAGE)

        search = _search(monkeypatch, handler)
        out = await search("上下文工程")
        assert seen["method"] == "POST"
        assert "q=%E4%B8%8A%E4%B8%8B%E6%96%87%E5%B7%A5%E7%A8%8B" in seen["body"]
        assert seen["ua"]  # a UA is sent so the endpoint does not block scripted requests
        assert "Result One" in out and "https://example.com/a" in out

    async def test_whitelist_denial(self, monkeypatch) -> None:
        search = _search(monkeypatch, lambda r: httpx.Response(200), domains=("github.com",))
        out = await search("q")
        assert "[已拒绝]" in out

    async def test_non_200_reports_failure(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="slow down")

        search = _search(monkeypatch, handler)
        out = await search("q")
        assert "[搜索失败]" in out and "503" in out

    async def test_empty_page_reports_no_result(self, monkeypatch) -> None:
        search = _search(monkeypatch, lambda r: httpx.Response(200, text="<html></html>"))
        out = await search("q")
        assert "[无结果]" in out

    async def test_empty_query_rejected(self, monkeypatch) -> None:
        search = _search(monkeypatch, lambda r: httpx.Response(200, text=_DDG_PAGE))
        out = await search("   ")
        assert "[参数无效]" in out


class TestSearchRedirect:
    """Redirects: the same per-hop validation as web_fetch."""

    async def test_redirect_followed_within_whitelist(self, monkeypatch) -> None:
        """First hop 302 -> a new address inside the whitelist: follows with GET and fetches the results page."""
        calls: list[tuple[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.host))
            if request.url.host == "html.duckduckgo.com":
                return httpx.Response(302, headers={"location": "https://duckduckgo.com/html2/"})
            return httpx.Response(200, text=_DDG_PAGE)

        search = _search(monkeypatch, handler)
        out = await search("q")
        assert calls == [("POST", "html.duckduckgo.com"), ("GET", "duckduckgo.com")]
        assert "Result One" in out

    async def test_redirect_to_off_whitelist_refused(self, monkeypatch) -> None:
        """302 -> an off-whitelist domain: that hop is refused and no request is sent."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "html.duckduckgo.com":
                return httpx.Response(302, headers={"location": "https://evil.example.com/x"})
            raise AssertionError(f"白名单外地址被实际请求: {request.url}")

        search = _search(monkeypatch, handler)
        out = await search("q")
        assert "[已拒绝]" in out

    async def test_redirect_loop_exhausted(self, monkeypatch) -> None:
        """Infinite redirects: exhausting the budget returns a clear failure instead of looping forever."""
        state = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            state["n"] += 1
            return httpx.Response(302, headers={"location": f"/hop{state['n']}"})

        search = _search(monkeypatch, handler)
        out = await search("q")
        assert "[搜索失败]" in out
        assert state["n"] <= 6  # capped by _MAX_REDIRECTS
