"""Usage-metering pipeline integration: agent reasoning goes through the
llm.complete capability -> the usage table accumulates -> get_usage_stats reports
non-zero totals.

Injection approach: do not use build(llm=FakeLLM) (that would let the agent
bypass the llm service capability and skip metering); instead, replace the
service's underlying client with one returning fixed completions, so the
capability guard chain and direct usage writes stay fully real.

The above refers only to the llm service usage table (TestUsageMetering below);
TestResourceQuotaFlow separately asserts the agent's in-process Meter, which
does not go through the llm service capability and instead uses
build(llm=FakeLLM). The two pipelines are intentionally not merged.
"""

import time

import pytest
from agent.llm import FakeLLM, LLMReply, Usage
from fastapi.testclient import TestClient
from host.assemble import build


@pytest.fixture()
def stub_llm_client(monkeypatch):
    """Replace the services/llm direct client: no network, fixed completions
    (still metered via the capability).

    Both transports (one-shot and streaming) must be stubbed, since chat turns go
    through complete_stream: the stream stub emits text deltas plus a final
    aggregate chunk with the same shape as llm.stream; the capability
    guard chain and direct usage writes stay fully real, and usage lands with the
    final chunk at the end of the stream.
    """
    from llm.capabilities import complete as llm_complete_mod
    from llm.capabilities import complete_stream as llm_stream_mod
    from llm.client import CompleteResult

    hits: list[str] = []

    async def fake_complete(
        provider,
        *,
        api_key,
        model,
        messages,
        max_tokens=4096,
        temperature=0.7,
        tools=None,
        reasoning_effort="",
    ):
        hits.append(model)
        return CompleteResult(
            text="ok.", input_tokens=12, output_tokens=6, model=model, tool_calls=()
        )

    def fake_stream(
        provider,
        *,
        api_key,
        model,
        messages,
        max_tokens=4096,
        temperature=0.7,
        tools=None,
        reasoning_effort="",
    ):
        async def _gen():
            hits.append(model)
            yield {"type": "text", "text": "ok."}
            yield {
                "type": "final",
                "text": "ok.",
                "tool_calls": [],
                "usage": {"input_tokens": 12, "output_tokens": 6},
                "model": model,
            }

        return _gen()

    monkeypatch.setattr(llm_complete_mod, "llm_complete", fake_complete)
    monkeypatch.setattr(llm_stream_mod, "llm_stream", fake_stream)
    return hits


class TestUsageMetering:
    def test_two_turns_metered_through_capability(
        self, tmp_path, monkeypatch, stub_llm_client
    ) -> None:
        monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", "usage-test-material")
        app = build(tmp_path / "data", tmp_path / "ws")
        with TestClient(app) as client:
            # Configure a usable provider: metadata via the capability, key
            # written by the user only (secrets are user-only)
            pid = client.post(
                "/api/llm/capabilities/add_provider",
                json={
                    "display_name": "metering test",
                    "base_url": "http://127.0.0.1:9",
                    "api_format": "chat",
                    "models": ["meter-model"],
                },
            ).json()["result"]["id"]
            resp = client.post(
                "/api/llm/capabilities/set_api_key",
                json={
                    "provider_id": pid,
                    "api_key": "sk-meter",
                },
            )
            assert resp.status_code == 200

            # Two chat turns: all agent reasoning goes through ServiceLLM ->
            # the llm.complete capability
            for _ in range(2):
                r = client.post("/api/chat/messages", json={"content": "ok"})
                assert r.status_code in (200, 202)

            deadline = time.time() + 8
            stats = {}
            while time.time() < deadline:
                stats = client.post(
                    "/api/llm/capabilities/get_usage_stats", json={"days": 30}
                ).json()["result"]
                if stats.get("calls", 0) >= 2:
                    break
                time.sleep(0.05)
            assert stats.get("calls", 0) >= 2, f"usage not accumulated: {stats}"
            assert stats["input_tokens"] >= 24  # at least 12 input tokens per turn
            assert stats["output_tokens"] >= 12
            models = {m["model"] for m in stats["by_model"]}
            assert "meter-model" in models  # per-model grouping (usage page table source)
            assert len(stub_llm_client) >= 2  # the underlying client really ran; chain is closed


class TestResourceQuotaFlow:
    def test_get_resource_quota_grows_with_chat(self, tmp_path) -> None:
        """The agent Meter quota capability grows with chat (resource dimension):
        the client injected via build(llm=FakeLLM) is still wrapped by
        build_agent's metered_llm, each complete's usage counts toward the day's
        usage, and get_resource_quota reads the same Meter.

        Note the accounting: this asserts the agent Meter (in-process), whereas
        TestUsageMetering above asserts the llm service usage table (persisted
        via the llm.complete capability). The two pipelines are independent and
        not merged."""
        llm = FakeLLM(
            dynamic=lambda m, t: LLMReply(text="ok.", usage=Usage(input_tokens=12, output_tokens=6))
        )
        app = build(tmp_path / "data", tmp_path / "ws", llm=llm)
        with TestClient(app) as client:
            # Set the quota high so chat is not blocked midway (a user_only
            # setting; the test identity is the local user)
            r = client.post(
                "/api/agent/capabilities/set_setting",
                json={"key": "agent.resource.daily_tokens", "value": 1_000_000},
            )
            assert r.status_code == 200

            client.post("/api/chat/messages", json={"content": "ok"})

            # Agent processing is asynchronous: poll until the meter counts it
            deadline = time.time() + 8
            quota = {}
            while time.time() < deadline:
                quota = client.post(
                    "/api/agent/capabilities/observe", json={"action": "quota"}
                ).json()["result"]
                if quota.get("tokens_used_today", 0) > 0:
                    break
                time.sleep(0.05)
            assert quota["tokens_used_today"] >= 18, f"quota did not grow with chat: {quota}"
            assert quota["daily_tokens"] == 1_000_000  # hot read of the setting works

    def test_quota_survives_backend_restart(self, tmp_path) -> None:
        """Restart the deployment root (rebuild with the same data_root): the
        agent Meter's llm metering is persisted synchronously via metered_llm to
        data_root/agent/meter.db, so after TestClient shutdown and reassembly the
        day's usage does not reset (no conversation replay)."""
        llm = FakeLLM(
            dynamic=lambda m, t: LLMReply(text="ok.", usage=Usage(input_tokens=12, output_tokens=6))
        )
        app = build(tmp_path / "data", tmp_path / "ws", llm=llm)
        with TestClient(app) as client:
            r = client.post(
                "/api/agent/capabilities/set_setting",
                json={"key": "agent.resource.daily_tokens", "value": 1_000_000},
            )
            assert r.status_code == 200
            client.post("/api/chat/messages", json={"content": "ok"})
            first = {}
            deadline = time.time() + 8
            while time.time() < deadline:
                first = client.post(
                    "/api/agent/capabilities/observe", json={"action": "quota"}
                ).json()["result"]
                if first.get("tokens_used_today", 0) > 0:
                    break
                time.sleep(0.05)
            assert first["tokens_used_today"] >= 18, (
                f"quota not accumulated before restart: {first}"
            )

        # Restart: reassemble with the same data_root, read the quota directly,
        # no conversation replay
        app2 = build(tmp_path / "data", tmp_path / "ws", llm=llm)
        with TestClient(app2) as client:
            quota = client.post("/api/agent/capabilities/observe", json={"action": "quota"}).json()[
                "result"
            ]
            assert quota["tokens_used_today"] >= first["tokens_used_today"] >= 18
