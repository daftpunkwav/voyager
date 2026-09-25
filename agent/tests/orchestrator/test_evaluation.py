"""Tests for task evaluation and feedback loop."""

from __future__ import annotations

from pathlib import Path

import pytest
from agent.llm import FakeLLM, LLMReply
from agent.memory import Memory
from agent.orchestrator.evaluation import (
    EvaluationResult,
    TaskEvaluator,
    get_recent_critiques,
    record_evaluation,
)
from agent.runtime.state import Step


def test_heuristic_evaluation_success() -> None:
    steps = [
        Step(n=1, kind="tool", name="read_file", summary="read ok", detail={"ok": True}),
        Step(n=2, kind="tool", name="list_dir", summary="list ok", detail={"ok": True}),
    ]
    res = TaskEvaluator.evaluate_heuristic(
        user_prompt="List files and read config",
        assistant_reply="Here is your file content and listing.",
        steps=steps,
    )
    assert res.score == 1.0
    assert res.passed is True
    assert res.rubric == "heuristic"
    assert "without errors" in res.feedback


def test_heuristic_evaluation_degraded() -> None:
    res = TaskEvaluator.evaluate_heuristic(
        user_prompt="Do something",
        assistant_reply="[LLM error] rate limited",
        degraded=True,
    )
    assert res.score == 0.0
    assert res.passed is False
    assert "Execution failed" in res.feedback


def test_heuristic_evaluation_tool_failures() -> None:
    steps = [
        Step(n=1, kind="tool", name="test_tool", summary="failed", detail={"ok": False}),
        Step(n=2, kind="tool", name="test_tool", summary="failed", detail={"ok": False}),
        Step(n=3, kind="tool", name="test_tool", summary="ok", detail={"ok": True}),
    ]
    res = TaskEvaluator.evaluate_heuristic(
        user_prompt="Run tools",
        assistant_reply="Completed with some errors.",
        steps=steps,
        min_score=0.7,
    )
    # 2/3 tool failure rate = 0.67 -> deduction 0.67 * 0.4 = 0.27 -> score ~ 0.73
    assert res.score < 1.0
    assert "Tool errors observed" in res.feedback
    assert res.metrics["tools_failed"] == 2
    assert res.metrics["tools_total"] == 3


def test_heuristic_circuit_breaker() -> None:
    res = TaskEvaluator.evaluate_heuristic(
        user_prompt="Run command",
        assistant_reply="[熔断] bash tool continuous failures.",
    )
    assert res.score <= 0.7
    assert "circuit breaker" in res.feedback


@pytest.mark.asyncio
async def test_judge_evaluation() -> None:
    fake_llm = FakeLLM(
        script=[
            LLMReply(
                text='{"score": 0.95, "feedback": "Clear explanation and all constraints satisfied."}'
            )
        ]
    )
    res = await TaskEvaluator.evaluate_judge(
        fake_llm,
        user_prompt="How does memory work?",
        assistant_reply="Memory is split into four zones...",
    )
    assert res.score == 0.95
    assert res.passed is True
    assert res.rubric == "judge"
    assert "Clear explanation" in res.feedback


@pytest.mark.asyncio
async def test_judge_evaluation_fallback_on_bad_json() -> None:
    fake_llm = FakeLLM(script=[LLMReply(text="Not a json response at all")])
    res = await TaskEvaluator.evaluate_judge(
        fake_llm,
        user_prompt="Test fallback",
        assistant_reply="Valid assistant answer",
    )
    assert res.rubric == "heuristic"
    assert res.passed is True


def test_record_and_get_recent_critiques(tmp_path: Path) -> None:
    mem = Memory(tmp_path)
    try:
        # Log passing eval
        good_eval = EvaluationResult(
            score=0.9, passed=True, rubric="heuristic", feedback="Good job"
        )
        record_evaluation(mem, good_eval, run_id="run_good")

        # Log failing eval
        bad_eval = EvaluationResult(
            score=0.4,
            passed=False,
            rubric="heuristic",
            feedback="Tool execution failed repeatedly, avoid invalid arguments.",
        )
        record_evaluation(mem, bad_eval, run_id="run_bad")

        critiques = get_recent_critiques(mem, limit=3)
        assert len(critiques) == 1
        assert "avoid invalid arguments" in critiques[0]

        # Verify episodic records
        records = mem.episodic.recent(limit=10, kind="evaluation")
        assert len(records) == 2
    finally:
        mem.close()
