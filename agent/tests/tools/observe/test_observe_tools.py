"""Aggregated observe + tools surfaces: read_events' allowlisted event feed,
the quota snapshot, and the roster list/describe/search actions."""

from __future__ import annotations

import json

from agent.build import build_agent
from agent.llm import FakeLLM, ToolCall
from agent.runtime import MeterRecord
from agent.tools import Toolbelt
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER

USER_CTX = ActorContext(actor=LOCAL_USER)


def _belt(app) -> Toolbelt:
    async def _yes(_prompt: str) -> bool:
        return True

    async def _noop(_msg: str) -> None:
        return None

    root = app.spawner._toolbelt
    return Toolbelt(dict(root._tools), root._policy, confirm=_yes, notify=_noop)


class TestObserveEvents:
    async def test_allowlist_and_incremental_cursor(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            belt = _belt(app)
            await execute(
                app.registry, "set_setting", USER_CTX, {"key": "agent.style", "value": "terse"}
            )
            out = json.loads(
                await belt.call(
                    ToolCall("1", "observe", {"action": "events", "types": ["settings.changed"]})
                )
            )
            assert out["events"] and out["events"][-1]["type"] == "settings.changed"
            assert out["events"][-1]["actor"] == "user:local"
            latest = out["latest_seq"]
            more = json.loads(
                await belt.call(
                    ToolCall(
                        "2",
                        "observe",
                        {
                            "action": "events",
                            "types": ["settings.changed"],
                            "after_seq": latest,
                        },
                    )
                )
            )
            assert more["events"] == []
            refused = json.loads(
                await belt.call(
                    ToolCall("3", "observe", {"action": "events", "types": ["agent.delta"]})
                )
            )
            assert refused["error"].startswith("[参数错误]")
        finally:
            app.close()


class TestQuotaAndRoster:
    async def test_quota(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            belt = _belt(app)
            app.meter.record(
                MeterRecord(kind="llm", name="t", ms=1.0, input_tokens=5, output_tokens=5)
            )
            quota = json.loads(await belt.call(ToolCall("1", "observe", {"action": "quota"})))
            assert quota == {
                "tokens_used_today": 10,
                "daily_tokens": 0,
                "cost_usd": 0.0,
                "cost_unknown_models": ["t"],  # unknown model: surfaced, not priced
            }
        finally:
            app.close()

    async def test_roster_list_and_describe(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            belt = _belt(app)
            roster = json.loads(await belt.call(ToolCall("1", "tools", {"action": "list"})))
            names = {t["name"] for t in roster}
            assert {"read", "agent_instance", "observe", "session"} <= names
            entry = next(t for t in roster if t["name"] == "session")
            assert entry["class"] in ("R", "D")
            detail = json.loads(
                await belt.call(ToolCall("2", "tools", {"action": "describe", "name": "todowrite"}))
            )
            assert "action" in detail["parameters"]["properties"]
        finally:
            app.close()
