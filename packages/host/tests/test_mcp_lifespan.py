"""mcp.start() is mounted in the background inside the lifespan and does not
block gateway readiness.

With a slow start (monkeypatched 2s sleep), entering TestClient still takes <1s
and /health reports all six domains up; on shutdown the task is cancelled and
awaited cleanly without leaking a pending task.
"""

import asyncio
import time

from agent.mcp.pool import McpClientPool
from fastapi.testclient import TestClient
from host.assemble import build

DOMAINS = {"llm", "sources", "notes", "graph", "settings", "agent"}


def test_slow_mcp_start_does_not_block_ready(tmp_path, monkeypatch) -> None:
    """With start connecting slowly for 2s, the gateway is ready in <1s; /health
    is normal; exit cancels cleanly."""
    cancelled: list[bool] = []

    async def slow_start(self) -> None:
        self._started = True  # preserve idempotent semantics
        try:
            await asyncio.sleep(2)  # simulate a slow preview (single-server CONNECT_TIMEOUT=15s)
        except asyncio.CancelledError:
            cancelled.append(True)  # shutdown cancels rather than waiting the full 2s
            raise

    monkeypatch.setattr(McpClientPool, "start", slow_start)

    app = build(tmp_path / "data", tmp_path / "ws")
    t0 = time.monotonic()
    with TestClient(app) as client:
        elapsed = time.monotonic() - t0
        assert elapsed < 1.0, f"TestClient entry took {elapsed:.2f}s, start blocked ready"
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert DOMAINS <= set(body["services"])
        assert all(s["status"] == "up" for s in body["services"].values())
    # Leaving the with block without raising = clean shutdown; the background
    # task was cancelled, not awaited to completion
    assert cancelled == [True]
