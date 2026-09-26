"""Tests for the self-contained MCP session implementations (stdio subprocess
and HTTP URL transports): the JSON-RPC framing, result parsing, error
propagation and teardown paths the injected fakes normally bypass.

Test type: unit (real subprocess / mocked HTTP transport, no pool wiring).
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import httpx
import pytest
from agent.mcp import session as session_module
from agent.mcp.session import StdioMcpSession, UrlMcpSession, default_connect

# An in-process MCP server speaking one newline-framed JSON-RPC message per
# stdin line: answers every request by method name, ignores notifications.
_SERVER_SCRIPT = r"""
import json, sys
print("server log noise", flush=True)
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
    except ValueError:
        continue
    if not isinstance(req, dict) or "id" not in req:
        continue
    method = req.get("method")
    rid = req["id"]
    if method == "initialize":
        result = {"capabilities": {"tools": {}}, "instructions": "be nice"}
    elif method == "tools/list":
        result = {"tools": [
            {"name": "echo", "description": "Echo", "inputSchema": {"type": "object"}},
            {"broken": True},
            "stray",
        ]}
    elif method == "tools/call":
        tool = (req.get("params") or {}).get("name") or ""
        if tool == "boom":
            print(json.dumps({"jsonrpc": "2.0", "id": rid,
                              "error": {"code": -32601, "message": "no such method"}}), flush=True)
            continue
        if tool == "empty_call":
            result = {"content": []}
        else:
            result = {"content": [
                {"type": "text", "text": "part1"},
                {"type": "image"},
                {"type": "text", "text": "part2:" + tool},
            ]}
    elif method == "resources/list":
        result = {"resources": [{"uri": "file:///x", "name": "x"}, {"no_uri": True}]}
    elif method == "resources/read":
        result = {"contents": [
            {"mimeType": "text/plain", "text": "hello"},
            {"uri": "file:///b.bin", "mimeType": "application/octet-stream"},
        ]}
    else:
        result = {"echo": method}
    print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}), flush=True)
"""


def _stdio_cfg(script: str) -> dict:
    return {"id": "s", "kind": "stdio", "command": sys.executable, "args": ["-c", script]}


async def _connect_stdio(script: str = _SERVER_SCRIPT) -> StdioMcpSession:
    session = await default_connect(_stdio_cfg(script))
    assert isinstance(session, StdioMcpSession)
    return session  # type: ignore[return-value]


class TestStdioSession:
    async def test_initialize_captures_capabilities_and_instructions(self) -> None:
        session = await _connect_stdio()
        try:
            assert session.server_capabilities == {"tools": {}}
            assert session.instructions == "be nice"
        finally:
            await session.aclose()

    async def test_list_remote_tools_normalizes_entries(self) -> None:
        session = await _connect_stdio()
        try:
            tools = await session.list_remote_tools()
            assert tools == [{"name": "echo", "description": "Echo", "schema": {"type": "object"}}]
        finally:
            await session.aclose()

    async def test_call_tool_joins_text_parts(self) -> None:
        session = await _connect_stdio()
        try:
            out = await session.call_tool("echo", {"q": "x"})
            assert out == "part1\npart2:echo"
            empty = await session.call_tool("empty_call", {})
            assert empty == '{"content": []}'  # falls back to the raw JSON result
        finally:
            await session.aclose()

    async def test_resources_round_trip_with_non_text_placeholder(self) -> None:
        session = await _connect_stdio()
        try:
            resources = await session.list_resources()
            assert resources == [
                {
                    "uri": "file:///x",
                    "name": "x",
                    "description": "",
                    "mimeType": "",
                }
            ]
            text = await session.read_resource("file:///x")
            assert "hello" in text
            assert "[non-text content: application/octet-stream]" in text
        finally:
            await session.aclose()

    async def test_error_response_raises_readable_runtime_error(self) -> None:
        session = await _connect_stdio()
        try:
            with pytest.raises(RuntimeError, match="JSON-RPC -32601: no such method"):
                await session.call_tool("boom", {})
        finally:
            await session.aclose()

    async def test_concurrent_requests_keep_their_own_responses(self) -> None:
        """The rpc lock serializes request/response pairs over the one stdout
        stream: interleaved calls each get their own answer, never a stolen one."""
        session = await _connect_stdio()
        try:
            names = [f"tool{i}" for i in range(5)]
            results = await asyncio.gather(*(session.call_tool(name, {}) for name in names))
            assert results == [f"part1\npart2:{name}" for name in names]
        finally:
            await session.aclose()

    async def test_subprocess_exit_raises_eof_error(self) -> None:
        session = StdioMcpSession(sys.executable, ["-c", "raise SystemExit"])
        await session.connect()
        with pytest.raises(RuntimeError, match="exited"):
            await session.list_remote_tools()
        await session.aclose()

    async def test_unconnected_session_fails_readably(self) -> None:
        session = StdioMcpSession(sys.executable, ["-c", "pass"])
        with pytest.raises(RuntimeError, match="not started"):
            await session.list_remote_tools()

    async def test_aclose_is_idempotent_and_close_sync_terminates(self) -> None:
        session = await _connect_stdio()
        session.close_sync()  # no event loop needed
        await asyncio.sleep(0.05)  # let the killed subprocess drain
        await session.aclose()  # double teardown stays quiet
        await session.aclose()


class TestSseResultParsing:
    def test_collects_data_lines_per_event(self) -> None:
        text = (
            "event: message\ndata: "
            '{"jsonrpc": "2.0", "id": 1, "result": {"ok": true}}\n\n'
            "data: not json\n\ndata: [1,2]\n\n"
        )
        msg = session_module._sse_result(text)
        assert msg == {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}

    def test_no_result_anywhere_raises(self) -> None:
        with pytest.raises(RuntimeError, match="no JSON-RPC result"):
            session_module._sse_result("data: [1,2]\n\nevent: ping\n\n")


class TestUrlSession:
    @pytest.fixture()
    def patch_client(self, monkeypatch):
        """Route every AsyncClient the session builds through a MockTransport."""

        def _install(handler: Any) -> list[dict]:
            seen: list[dict] = []

            def _handler(request: httpx.Request) -> httpx.Response:
                import json as _json

                seen.append(
                    {
                        "url": str(request.url),
                        "payload": _json.loads(request.content.decode() or "null"),
                        "accept": request.headers.get("accept", ""),
                    }
                )
                return handler(request)

            original = httpx.AsyncClient  # captured before the patch below

            def _factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
                kwargs.pop("transport", None)
                return original(*args, transport=httpx.MockTransport(_handler), **kwargs)

            monkeypatch.setattr(session_module.httpx, "AsyncClient", _factory)
            return seen

        return _install

    async def test_json_request_round_trip_and_notification(self, patch_client) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            import json as _json

            payload = _json.loads(request.content.decode())
            if "id" not in payload:
                return httpx.Response(202)
            if payload["method"] == "initialize":
                result: dict[str, Any] = {"capabilities": {}, "instructions": "http rules"}
            else:
                result = {"tools": [{"name": "t1", "description": "d"}]}
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result}
            )

        seen = patch_client(handler)
        session = UrlMcpSession("https://mcp.example.test/rpc")
        await session.connect()
        try:
            await session.initialize()
            assert session.instructions == "http rules"
            tools = await session.list_remote_tools()
            assert tools[0]["name"] == "t1"
        finally:
            await session.aclose()
        assert seen[0]["accept"] == "application/json, text/event-stream"
        # the initialized notification carried no id and got its 202
        assert "id" not in seen[1]["payload"]

    async def test_sse_response_is_parsed_from_data_lines(self, patch_client) -> None:
        import json as _json

        def handler(request: httpx.Request) -> httpx.Response:
            payload = _json.loads(request.content.decode())
            body = (
                "event: message\ndata: "
                + _json.dumps({"jsonrpc": "2.0", "id": payload["id"], "result": {"tools": []}})
                + "\n\n"
            )
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

        patch_client(handler)
        session = UrlMcpSession("https://mcp.example.test/sse")
        await session.connect()
        try:
            assert await session.list_remote_tools() == []
        finally:
            await session.aclose()

    async def test_error_result_raises_readable_error(self, patch_client) -> None:
        import json as _json

        def handler(request: httpx.Request) -> httpx.Response:
            payload = _json.loads(request.content.decode())
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "error": {"code": -32000, "message": "denied"},
                },
            )

        patch_client(handler)
        session = UrlMcpSession("https://mcp.example.test/rpc")
        await session.connect()
        try:
            with pytest.raises(RuntimeError, match="JSON-RPC -32000: denied"):
                await session.list_remote_tools()
        finally:
            await session.aclose()

    async def test_empty_body_and_non_dict_body_raise_readably(self, patch_client) -> None:
        patch_client(lambda request: httpx.Response(200))
        session = UrlMcpSession("https://mcp.example.test/rpc")
        await session.connect()
        try:
            with pytest.raises(RuntimeError, match="no response"):
                await session.list_remote_tools()
        finally:
            await session.aclose()

    async def test_http_error_status_propagates(self, patch_client) -> None:
        patch_client(lambda request: httpx.Response(500, text="down"))
        session = UrlMcpSession("https://mcp.example.test/rpc")
        await session.connect()
        try:
            with pytest.raises(httpx.HTTPStatusError):
                await session.list_remote_tools()
        finally:
            await session.aclose()

    async def test_unconnected_session_fails_readably(self) -> None:
        session = UrlMcpSession("https://mcp.example.test/rpc")
        with pytest.raises(RuntimeError, match="not connected"):
            await session.list_remote_tools()

    async def test_teardown_paths(self) -> None:
        session = UrlMcpSession("https://mcp.example.test/rpc")
        session.close_sync()  # before connect: just drops the (absent) client
        await session.aclose()
        await session.connect()
        session.close_sync()  # GC hand-off without a loop
        await session.aclose()  # idempotent


class TestDefaultConnect:
    async def test_url_kind_builds_http_session(self, monkeypatch) -> None:
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json as _json

            payload = _json.loads(request.content.decode())
            if "id" not in payload:
                return httpx.Response(202)
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"capabilities": {}, "instructions": ""},
                },
            )

        original = httpx.AsyncClient  # captured before the patch below

        def _factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
            captured["created"] = True
            kwargs.pop("transport", None)
            return original(*args, transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(session_module.httpx, "AsyncClient", _factory)
        session = await default_connect({"id": "u", "kind": "url", "url": "https://x.test"})
        assert isinstance(session, UrlMcpSession)
        await session.aclose()
        assert captured["created"] is True

    async def test_failed_handshake_releases_resources_and_reraises(self) -> None:
        """A server that dies before answering makes initialize fail; the
        half-open session is torn down and the original error propagates."""
        with pytest.raises(RuntimeError):
            await default_connect(
                {"id": "d", "kind": "stdio", "command": sys.executable, "args": ["-c", "pass"]}
            )
