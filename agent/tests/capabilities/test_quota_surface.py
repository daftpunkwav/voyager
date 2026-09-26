"""Domain capability REST surface: agent and human invoke the same
capability with the same standing."""

import pytest
from agent.llm import FakeLLM
from agent.main import build_agent
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ActorKind, ActorRef

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


@pytest.fixture()
def app(tmp_path):
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
    yield app
    app.memory.close()


from agent.runtime import MeterRecord


class TestResourceQuota:
    """get_resource_quota (resource dimension): read-only view of today usage,
    the estimated cost, and the quota limit."""

    async def test_empty_meter_defaults(self, app) -> None:
        """Empty meter: usage 0, no cost, no unknown models; daily_tokens reads the settings default of 0 (= unlimited)."""
        result = await execute(app.registry, "observe", USER_CTX, {"action": "quota"})
        assert result == {
            "tokens_used_today": 0,
            "daily_tokens": 0,
            "cost_usd": 0.0,
            "cost_unknown_models": [],
        }

    async def test_reports_usage_and_limit(self, app) -> None:
        """Pre-seeded today records plus a limit: the reply matches Meter / settings (records default to ts=today)."""
        app.meter.record(
            MeterRecord(kind="llm", name="test", ms=1.0, input_tokens=300, output_tokens=70)
        )
        await execute(
            app.registry,
            "set_setting",
            USER_CTX,
            {"key": "agent.resource.daily_tokens", "value": 1000},
        )
        result = await execute(app.registry, "observe", USER_CTX, {"action": "quota"})
        assert result == {
            "tokens_used_today": 370,
            "daily_tokens": 1000,
            "cost_usd": 0.0,
            "cost_unknown_models": ["test"],  # unknown model: surfaced, never priced at zero
        }

    async def test_agent_can_read_own_quota(self, app) -> None:
        """Parity: the agent can query its own quota (intended use: checking how much allowance is left)."""
        await execute(
            app.registry,
            "set_setting",
            USER_CTX,
            {"key": "agent.resource.daily_tokens", "value": 500},
        )
        result = await execute(
            app.registry,
            "observe",
            AGENT_CTX,
            {"action": "quota"},
        )
        assert result == {
            "tokens_used_today": 0,
            "daily_tokens": 500,
            "cost_usd": 0.0,
            "cost_unknown_models": [],
        }
