"""Minimal MCP session implementation: stdio subprocess and HTTP URL paths.

Minimal protocol set (JSON-RPC 2.0): initialize -> notifications/initialized
-> tools/list / tools/call. The root pyproject has no hard dependency on the
mcp SDK, so this self-contained implementation keeps things working; tests
inject fakes through the pool's connect and never exercise this module.

Framing: the MCP stdio spec (since 2024-11-05) frames by **newline**, one
JSON-RPC message per line - not LSP Content-Length. Non-JSON lines (logs from
some servers) are ignored.
"""

from __future__ import annotations

import asyncio
import itertools
import json
from contextlib import suppress
from typing import Any, Protocol, runtime_checkable

import httpx

#: Protocol version used in the initialize handshake (long-term compatibility line)
PROTOCOL_VERSION = "2024-11-05"

CALL_TIMEOUT = 30.0  # per-request cap for the HTTP client (seconds); stdio call timeouts are wrapped with wait_for at call time in mount.py


@runtime_checkable
class McpSession(Protocol):
    """Session with one external MCP server; production implementations are in
    this file, tests inject fakes."""

    async def list_remote_tools(self) -> list[dict]:
        """Remote tool list; each entry has at least {name, description, schema?}."""
        ...

    async def call_tool(self, name: str, arguments: dict) -> str:
        """Call a remote tool, returning the concatenated text result."""
        ...

    async def aclose(self) -> None:
        """Disconnect (kill subprocess / close HTTP client); safe to call repeatedly."""
        ...


class _McpProtocol:
    """Minimal MCP protocol over JSON-RPC 2.0; transports implement
    connect/_request/_notify in subclasses."""

    _ids = itertools.count(1)

    def __init__(self) -> None:
        self.server_capabilities: dict = {}  # from the initialize result
        self.instructions: str = ""  # server-declared usage instructions (may be empty)

    async def connect(self) -> None:
        raise NotImplementedError

    async def _request(self, method: str, params: dict | None) -> Any:
        raise NotImplementedError

    async def aclose(self) -> None:
        raise NotImplementedError

    async def _notify(self, method: str, params: dict | None) -> None:
        raise NotImplementedError

    async def initialize(self) -> None:
        result = await self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "agent", "version": "1.0"},
            },
        )
        if isinstance(result, dict):
            caps = result.get("capabilities")
            self.server_capabilities = caps if isinstance(caps, dict) else {}
            raw_instructions = result.get("instructions")
            self.instructions = str(raw_instructions) if raw_instructions else ""
        await self._notify("notifications/initialized", {})

    async def list_remote_tools(self) -> list[dict]:
        result = await self._request("tools/list", {})
        tools = result.get("tools") or [] if isinstance(result, dict) else []
        return [
            {
                "name": str(t.get("name") or ""),
                "description": str(t.get("description") or ""),
                "schema": t.get("inputSchema") or {},
            }
            for t in tools
            if isinstance(t, dict) and t.get("name")
        ]

    async def call_tool(self, name: str, arguments: dict) -> str:
        result = await self._request("tools/call", {"name": name, "arguments": arguments})
        if not isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False)
        # content is [{type:"text",text:...},...]; concatenate the text, falling
        # back to the raw JSON when empty
        parts = [
            str(c.get("text") or "")
            for c in (result.get("content") or [])
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        text = "\n".join(p for p in parts if p)
        return text or json.dumps(result, ensure_ascii=False)

    async def list_resources(self) -> list[dict]:
        """Resource list for servers declaring the capability; each entry has
        {uri, name, description?, mimeType?}."""
        result = await self._request("resources/list", {})
        resources = result.get("resources") or [] if isinstance(result, dict) else []
        return [
            {
                "uri": str(r.get("uri") or ""),
                "name": str(r.get("name") or ""),
                "description": str(r.get("description") or ""),
                "mimeType": str(r.get("mimeType") or ""),
            }
            for r in resources
            if isinstance(r, dict) and r.get("uri")
        ]

    async def read_resource(self, uri: str) -> str:
        """Read one resource; text contents are concatenated (non-text
        contents render as a placeholder line)."""
        result = await self._request("resources/read", {"uri": uri})
        if not isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False)
        parts: list[str] = []
        for c in result.get("contents") or []:
            if not isinstance(c, dict):
                continue
            if isinstance(c.get("text"), str):
                parts.append(c["text"])
            else:
                parts.append(f"[non-text content: {c.get('mimeType') or c.get('uri') or '?'}]")
        return "\n".join(p for p in parts if p) or json.dumps(result, ensure_ascii=False)


class StdioMcpSession(_McpProtocol):
    """stdio subprocess session. command+args are exec'd directly
    (shell=False, never shell=True)."""

    def __init__(self, command: str, args: list[str], cwd: str | None = None) -> None:
        super().__init__()
        self._command = command
        self._args = list(args)
        self._cwd = cwd
        self._proc: asyncio.subprocess.Process | None = None
        self._rpc_lock = (
            asyncio.Lock()
        )  # serialize request-response: concurrent reads would steal each other's response lines

    async def connect(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            self._command,
            *self._args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,  # subprocess logs must not mix into the protocol stream
            cwd=self._cwd,
        )

    async def _send(self, payload: dict) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise RuntimeError("MCP subprocess not started")
        proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())
        await proc.stdin.drain()

    async def _read_result(self, want_id: int) -> Any:
        proc = self._proc
        if proc is None or proc.stdout is None:
            raise RuntimeError("MCP subprocess not started")
        while True:
            line = await proc.stdout.readline()
            if not line:
                raise RuntimeError("MCP subprocess exited (stdout EOF)")
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue  # non-JSON lines (server logs) stay out of the protocol
            if not isinstance(msg, dict) or msg.get("id") != want_id:
                continue  # notifications / server-initiated requests (e.g. sampling) ignored for now
            if msg.get("error"):
                err = msg["error"] or {}
                raise RuntimeError(f"JSON-RPC {err.get('code')}: {err.get('message')}")
            return msg.get("result")

    async def _request(self, method: str, params: dict | None) -> Any:
        # One subprocess stdout is a single-consumer stream: concurrent request
        # read loops would steal each other's response lines (a skipped id
        # mismatch is lost forever), so the whole section must be serialized.
        async with self._rpc_lock:
            rid = next(self._ids)
            await self._send(
                {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
            )
            return await self._read_result(rid)

    async def _notify(self, method: str, params: dict | None) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    async def aclose(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.returncode is not None:
            return
        with suppress(Exception):
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 5)
            except TimeoutError:
                proc.kill()

    def close_sync(self) -> None:
        """Best-effort teardown without an event loop (AgentApp.close is sync):
        terminate directly, no waiting."""
        proc, self._proc = self._proc, None
        if proc is not None and proc.returncode is None:
            with suppress(Exception):
                proc.terminate()


def _sse_result(text: str) -> Any:
    """Parse SSE text: collect data: lines per event into JSON, returning the
    first message carrying result/error."""
    for block in text.split("\n\n"):
        data_lines = [ln[5:].strip() for ln in block.splitlines() if ln.startswith("data:")]
        if not data_lines:
            continue
        try:
            msg = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            continue
        if isinstance(msg, dict) and ("result" in msg or "error" in msg):
            return msg
    raise RuntimeError("no JSON-RPC result in the SSE response")


class UrlMcpSession(_McpProtocol):
    """HTTP session: each JSON-RPC message is POSTed to the configured URL
    (simplest form, no session headers).

    Responses come in two shapes: application/json read directly;
    text/event-stream parsed from data: lines. Notifications
    (notifications/initialized etc.) treat 202/empty body as success.
    """

    def __init__(self, url: str, timeout: float = CALL_TIMEOUT) -> None:
        super().__init__()
        self._url = url
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def _post(self, payload: dict) -> Any:
        client = self._client
        if client is None:
            raise RuntimeError("MCP HTTP session not connected")
        resp = await client.post(
            self._url,
            json=payload,
            headers={"Accept": "application/json, text/event-stream"},
        )
        resp.raise_for_status()
        if resp.status_code == 202 or not resp.content.strip():
            return None
        if "text/event-stream" in resp.headers.get("content-type", ""):
            return _sse_result(resp.text)
        return resp.json()

    async def _request(self, method: str, params: dict | None) -> Any:
        rid = next(self._ids)
        msg = await self._post(
            {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
        )
        if not isinstance(msg, dict):
            # RuntimeError is right (protocol failure), not an argument type error
            raise RuntimeError(f"MCP server returned no response for {method}")  # noqa: TRY004
        if msg.get("error"):
            err = msg["error"] or {}
            raise RuntimeError(f"JSON-RPC {err.get('code')}: {err.get('message')}")
        return msg.get("result")

    async def _notify(self, method: str, params: dict | None) -> None:
        await self._post({"jsonrpc": "2.0", "method": method, "params": params or {}})

    async def aclose(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            with suppress(Exception):
                await client.aclose()

    def close_sync(self) -> None:
        """Best-effort teardown without an event loop: the HTTP client is left to
        the GC; dropping the reference deactivates it."""
        self._client = None


async def default_connect(cfg: dict) -> McpSession:
    """Production connect: kind=stdio spawns a subprocess (shell=False);
    kind=url uses HTTP.

    Returns only after the initialize handshake completes; a handshake failure
    releases resources and re-raises unchanged for the pool to turn into a
    readable error.
    """
    if cfg.get("kind") == "stdio":
        session: _McpProtocol = StdioMcpSession(
            str(cfg["command"]), list(cfg.get("args") or []), cfg.get("cwd")
        )
    else:
        session = UrlMcpSession(str(cfg["url"]))
    try:
        await session.connect()
        await session.initialize()
    except Exception:
        with suppress(Exception):
            await session.aclose()
        raise
    return session  # type: ignore[return-value]
