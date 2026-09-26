"""MCP client resilience tests: stdio request serialization, preview
connection races, and shutdown logging.
"""

import asyncio

from agent.mcp.pool import McpClientPool
from agent.mcp.session import StdioMcpSession, UrlMcpSession


class TestStdioSerialization:
    async def test_concurrent_requests_do_not_interleave(self) -> None:
        """Concurrent _request calls serialize whole sections under the lock: send+read never interleave (otherwise response lines get stolen)."""
        session = StdioMcpSession("noop", [])
        timeline: list[str] = []

        async def fake_send(payload: dict) -> None:
            timeline.append(f"send:{payload['id']}")

        async def fake_read(rid: int) -> dict:
            await asyncio.sleep(
                0.01
            )  # yields a suspension point: without the lock the other request would interleave
            timeline.append(f"read:{rid}")
            return {"ok": rid}

        session._send = fake_send  # type: ignore[method-assign]  # test stub
        session._read_result = fake_read  # type: ignore[method-assign, assignment]  # test stub

        out = await asyncio.gather(
            session._request("tools/list", {}),
            session._request("tools/call", {}),
        )
        assert out == [{"ok": 1}, {"ok": 2}]
        # Serial shape: each request's send/read are adjacent pairs with no interleaving
        pairs = [(timeline[i], timeline[i + 1]) for i in range(0, len(timeline), 2)]
        for send_ev, read_ev in pairs:
            assert send_ev.startswith("send:")
            assert read_ev == f"read:{send_ev.split(':')[1]}"

    def test_url_session_has_close_sync(self) -> None:
        """URL sessions provide close_sync so the pool sync shutdown path no longer skips them."""
        s = UrlMcpSession("https://example.com/mcp")
        assert callable(getattr(s, "close_sync", None))
        s.close_sync()
        assert s._client is None  # dropping the reference deactivates the session


class TestPreviewRace:
    async def test_concurrent_previews_share_one_connection(self, tmp_path) -> None:
        """Concurrent previews of one server: a single connection is created and latecomers reuse it (no leak)."""
        connects = {"n": 0}

        class FakeSession:
            async def call_tool(self, name: str, arguments: dict) -> str:
                return ""

            async def list_remote_tools(self) -> list[dict]:
                await asyncio.sleep(0.01)
                return [{"name": "t", "description": "d", "schema": {}}]

            async def aclose(self) -> None:
                return None

        async def fake_connect(cfg: dict) -> FakeSession:
            connects["n"] += 1
            await asyncio.sleep(0.02)  # create a race window
            return FakeSession()

        class FakeSettings:
            def get(self, key: str):
                return [
                    {
                        "id": "srv",
                        "name": "srv",
                        "kind": "url",
                        "url": "https://example.com/mcp",
                        "approval": "package",
                    }
                ]

        pool = McpClientPool(settings=FakeSettings(), connect=fake_connect)
        tools = await asyncio.gather(pool.preview("srv"), pool.preview("srv"))
        assert tools[0] == tools[1]
        assert connects["n"] == 1  # the connection is created exactly once
        assert len(pool._sessions) == 1

    async def test_drop_session_logs_close_failure(self, tmp_path, caplog) -> None:
        import logging

        class BadSession:
            async def aclose(self) -> None:
                raise RuntimeError("pipe broken")

        pool = McpClientPool()
        pool._sessions["srv"] = BadSession()  # type: ignore[assignment]
        with caplog.at_level(logging.WARNING, logger="agent.mcp"):
            await pool.drop_session("srv")  # must not raise
        assert any("failed to disconnect MCP session" in r.message for r in caplog.records)
        assert pool._sessions == {}  # the entry is still removed
