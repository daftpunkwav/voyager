"""Tests for the streaming capability contract: flag, execute() validation,
REST rejection.
"""

from dataclasses import dataclass

import pytest
from platform_actor import ActorContext
from platform_capability import Registry, capability, execute
from platform_contracts import LOCAL_USER, ServiceError

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient
from platform_capability.gen_rest import build_router

USER_CTX = ActorContext(actor=LOCAL_USER)


@dataclass
class _In:
    q: str = ""


def _stream_registry() -> Registry:
    reg = Registry("llm")

    @capability(reg, name="gen", description="streaming test", streaming=True)
    async def gen(q: str = ""):
        async def _it():
            yield {"type": "text", "text": "hello"}
            yield {"type": "text", "text": "world"}

        return _it()

    @capability(
        reg, name="bad_gen", description="violates contract: returns a plain dict", streaming=True
    )
    async def bad_gen(q: str = ""):
        return {"text": "not a stream"}

    return reg


class TestExecuteContract:
    async def test_streaming_returns_async_iterator(self) -> None:
        reg = _stream_registry()
        out = await execute(reg, "gen", USER_CTX, {"q": "hi"})
        chunks = [c async for c in out]
        assert chunks == [
            {"type": "text", "text": "hello"},
            {"type": "text", "text": "world"},
        ]

    async def test_non_iterable_result_rejected(self) -> None:
        """A streaming capability returning a plain value is rejected by
        execute() with INTERNAL (mirrors long_running -> JobRef)."""
        reg = _stream_registry()
        with pytest.raises(ServiceError) as exc:
            await execute(reg, "bad_gen", USER_CTX, {"q": "hi"})
        assert exc.value.body.code == "LLM.INTERNAL"
        assert "async iterable" in exc.value.body.message

    async def test_non_streaming_capability_unchanged(self) -> None:
        reg = Registry("x")

        @capability(reg, name="plain", description="plain capability")
        async def plain() -> dict:
            return {"ok": True}

        assert await execute(reg, "plain", USER_CTX, {}) == {"ok": True}


class TestRestRejection:
    def test_streaming_rejected_503_handler_not_run(self, tmp_path) -> None:
        """Calling a streaming capability over REST: explicit 503 rejection;
        the handler never runs (call count stays 0)."""
        reg = _stream_registry()
        calls = {"gen": 0}

        @capability(reg, name="counted", description="counter", streaming=True)
        async def counted(q: str = ""):
            calls["gen"] += 1

            async def _it():
                yield {"type": "text", "text": "x"}

            return _it()

        app = FastAPI()
        app.include_router(build_router(reg))
        client = TestClient(app)
        resp = client.post("/capabilities/gen", json={"q": "hi"})
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "LLM.UNAVAILABLE"
        assert "in-process" in resp.json()["error"]["message"]
        assert calls["gen"] == 0  # rejection happens before guards and handler

    def test_listing_shows_streaming_flag(self, tmp_path) -> None:
        reg = _stream_registry()
        app = FastAPI()
        app.include_router(build_router(reg))
        client = TestClient(app)
        specs = {s["name"]: s for s in client.get("/capabilities").json()["capabilities"]}
        assert specs["gen"]["streaming"] is True
        assert specs["bad_gen"]["streaming"] is True
