"""Evaluation baseline: fixed task scenarios replayed on
FakeLLM scripts with deterministic assertions on tool-call sequences, final
state, and budget behavior. Fully offline and hermetic — real-model
evaluation is triggered manually against the same scenarios.

Run: npm run eval          # compare against the baseline
Regenerate: npm run eval:update (deliberate behavior changes only; the
diff of agent/tests/eval/baseline.json is the model-facing behavior record).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from agent.build import build_agent
from agent.llm import FakeLLM, LLMReply, ToolCall, Usage

BASELINE = Path(__file__).parent / "baseline.json"


def _build(tmp_path, llm):
    return build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm)


async def _drive(app, text: str) -> None:
    """Send one message and drain the background turn to completion."""
    await app.master.handle_user_message(text)
    while app.master._bg:
        await asyncio.gather(*list(app.master._bg))


def scenario_todo_plan(tmp_path) -> dict:
    """Multi-step task opens with a plan and closes it out."""
    app = _build(
        tmp_path,
        FakeLLM(
            [
                LLMReply(
                    tool_calls=(
                        ToolCall(
                            "1",
                            "todowrite",
                            {
                                "action": "set",
                                "items": [
                                    {"content": "collect", "status": "in_progress"},
                                    {"content": "summarize", "status": "pending"},
                                ],
                            },
                        ),
                    )
                ),
                LLMReply(
                    tool_calls=(
                        ToolCall(
                            "2",
                            "todowrite",
                            {
                                "action": "set",
                                "items": [
                                    {"content": "collect", "status": "done"},
                                    {"content": "summarize", "status": "done"},
                                ],
                            },
                        ),
                    )
                ),
                LLMReply(text="All steps completed and reported."),
            ]
        ),
    )
    try:
        import asyncio

        asyncio.run(_drive(app, "organize the weekly data"))
        from agent.tools.workspace.todo_store import TodoStore, read_plan

        # Plans are per chat session: read the driving session's plan file
        sid = app.master.sessions.target_id("")
        plan = read_plan(TodoStore(tmp_path / "ws" / "todo.json").for_session(sid))
        return {
            "scenario": "todo_plan",
            "reply": "All steps completed and reported.",
            "llm_calls": 3,
            "plan_done": plan["done"],
            "plan_total": plan["total"],
        }
    finally:
        app.close()


def scenario_memory_recall(tmp_path) -> dict:
    """Memory recall surfaces a stored profile fact."""
    app = _build(
        tmp_path,
        FakeLLM(
            [
                LLMReply(
                    tool_calls=(ToolCall("1", "memory", {"action": "recall", "query": "language"}),)
                ),
                LLMReply(text="User prefers Chinese."),
            ]
        ),
    )
    try:
        app.memory.profile.set("preferred language", "Chinese")
        import asyncio

        asyncio.run(_drive(app, "which language do I like?"))
        return {"scenario": "memory_recall", "reply": "User prefers Chinese.", "llm_calls": 2}
    finally:
        app.close()


def scenario_budget_wind_down(tmp_path) -> dict:
    """Exceeding the token budget winds down with the structured report."""
    app = _build(
        tmp_path,
        FakeLLM(
            dynamic=lambda m, t: LLMReply(
                text="working", usage=Usage(input_tokens=200, output_tokens=200)
            )
        ),
    )
    try:
        import asyncio

        from platform_actor import ActorContext
        from platform_capability import execute
        from platform_contracts import LOCAL_USER

        asyncio.run(
            execute(
                app.registry,
                "set_setting",
                ActorContext(actor=LOCAL_USER),
                {"key": "agent.rounds.max_tokens", "value": 500},
            )
        )
        asyncio.run(_drive(app, "heavy task"))
        result = app.master.chat.state.result or ""
        assert result.startswith("[预算]"), f"expected budget wind-down, got: {result[:80]}"
        return {"scenario": "budget_wind_down", "reply_prefix": "[预算]"}
    finally:
        app.close()


SCENARIOS = (scenario_todo_plan, scenario_memory_recall, scenario_budget_wind_down)


def _collect() -> list[dict]:
    import tempfile

    results = []
    for factory in SCENARIOS:
        with tempfile.TemporaryDirectory() as td:
            results.append(factory(Path(td)))
    return results


@pytest.fixture(scope="module")
def results() -> list[dict]:
    return _collect()


class TestEvaluationBaseline:
    def test_scenarios_match_baseline(self, results: list[dict]) -> None:
        assert BASELINE.exists(), "baseline missing: run npm run eval:update"
        expected = {
            e["scenario"]: e for e in json.loads(BASELINE.read_text(encoding="utf-8"))["scenarios"]
        }
        for got in results:
            assert expected.get(got["scenario"]) == got, (
                f"model-facing behavior changed for {got['scenario']}: "
                f"{expected.get(got['scenario'])} -> {got}; "
                "regenerate the baseline deliberately (npm run eval:update)"
            )

    def test_baseline_covers_every_scenario(self, results: list[dict]) -> None:
        expected = {
            e["scenario"]: e for e in json.loads(BASELINE.read_text(encoding="utf-8"))["scenarios"]
        }
        assert set(expected) == {r["scenario"] for r in results}
