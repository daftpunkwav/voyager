"""Task completion evaluation and feedback loop.

Provides deterministic heuristic evaluation and optional LLM-as-a-judge
evaluation, logging feedback to episodic memory to close the self-improvement
loop across turns.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from agent.llm import LLMClient
from agent.runtime.state import Step

log = logging.getLogger("agent.runtime.evaluation")


@dataclass(frozen=True)
class EvaluationResult:
    """Outcome of evaluating one turn or task execution."""

    score: float  # 0.0 to 1.0
    passed: bool  # whether score meets the threshold
    rubric: str  # rubric mode: "heuristic" | "judge"
    feedback: str  # diagnosis, rationale, or improvement suggestion
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "passed": self.passed,
            "rubric": self.rubric,
            "feedback": self.feedback,
            "metrics": self.metrics,
        }


class TaskEvaluator:
    """Evaluates task execution quality and produces diagnostic feedback."""

    @staticmethod
    def evaluate_heuristic(
        user_prompt: str,
        assistant_reply: str,
        steps: list[Step] | None = None,
        *,
        task_goal: str = "",
        degraded: bool = False,
        min_score: float = 0.6,
    ) -> EvaluationResult:
        """Fast, zero-overhead heuristic evaluation."""
        reply_text = (
            assistant_reply if isinstance(assistant_reply, str) else str(assistant_reply or "")
        )
        score = 1.0
        feedback_parts: list[str] = []
        empty_reply = not reply_text.strip()

        # 1. Check degradation and failure indicators
        if degraded or reply_text.startswith(("[LLM error]", "(Turn failed:")):
            score = 0.0
            feedback_parts.append("Execution failed or returned degraded response.")
        elif empty_reply:
            score = max(0.0, score - 0.5)
            feedback_parts.append("Assistant returned empty reply.")

        # 2. Check tool execution quality
        tools_total = 0
        tools_failed = 0
        if steps:
            for s in steps:
                if getattr(s, "kind", "") == "tool":
                    tools_total += 1
                    detail = getattr(s, "detail", None)
                    if isinstance(detail, dict) and detail.get("ok") is False:
                        tools_failed += 1

        if tools_total > 0:
            failure_rate = tools_failed / tools_total
            score -= failure_rate * 0.4
            if failure_rate > 0.0:
                feedback_parts.append(
                    f"Tool errors observed ({tools_failed}/{tools_total} failed)."
                )

        # 3. Check loop or circuit breaking indicators in reply
        if any(mark in reply_text for mark in ("[熔断]", "[循环]", "已达上限")):
            score = max(0.0, score - 0.3)
            feedback_parts.append("Interrupted by loop protection or circuit breaker.")

        score = max(0.0, min(1.0, round(score, 2)))
        passed = score >= min_score
        feedback = (
            " ".join(feedback_parts) if feedback_parts else "Turn completed cleanly without errors."
        )

        return EvaluationResult(
            score=score,
            passed=passed,
            rubric="heuristic",
            feedback=feedback,
            metrics={
                "tools_total": tools_total,
                "tools_failed": tools_failed,
                "degraded": bool(degraded) or score == 0.0,
                "empty_reply": empty_reply,
            },
        )

    @staticmethod
    async def evaluate_judge(
        llm: LLMClient,
        user_prompt: str,
        assistant_reply: str,
        *,
        task_goal: str = "",
        min_score: float = 0.6,
    ) -> EvaluationResult:
        """LLM-as-a-judge evaluation mode."""
        try:
            goal_text = task_goal if isinstance(task_goal, str) else str(task_goal or "")
            prompt_text = user_prompt if isinstance(user_prompt, str) else str(user_prompt or "")
            reply_text = (
                assistant_reply if isinstance(assistant_reply, str) else str(assistant_reply or "")
            )
            judge_prompt = (
                "You are an impartial evaluator assessing an AI assistant turn.\n"
                f"Goal: {goal_text or prompt_text}\n"
                f"User input: {prompt_text}\n"
                f"Assistant reply: {reply_text[:1500]}\n\n"
                "Evaluate if the assistant properly addressed the request. "
                "Output ONLY a JSON object with 'score' (float between 0.0 and 1.0) and "
                "'feedback' (short explanation or advice for improvement):\n"
                '{"score": 0.9, "feedback": "Clear and complete response."}'
            )
            reply = await llm.complete(
                [
                    {
                        "role": "system",
                        "content": "You are an evaluation engine. Reply strictly in JSON.",
                    },
                    {"role": "user", "content": judge_prompt},
                ]
            )
            raw = (reply.text or "").strip()
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.startswith("json"):
                    raw = raw[4:].strip()
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise TypeError(f"judge reply is not a JSON object: {raw[:80]!r}")
            score = float(data.get("score", 0.7))
            score = max(0.0, min(1.0, round(score, 2)))
            feedback = str(data.get("feedback", "")).strip() or "Evaluation completed."
            return EvaluationResult(
                score=score,
                passed=score >= min_score,
                rubric="judge",
                feedback=feedback,
                metrics={"judge_model": reply.model},
            )
        except Exception as exc:  # noqa: BLE001  # judge LLM failure falls back to heuristic
            log.warning("judge evaluation failed, falling back to heuristic: %s", exc)
            return TaskEvaluator.evaluate_heuristic(
                user_prompt, assistant_reply, task_goal=task_goal, min_score=min_score
            )


def record_evaluation(memory: Any, result: EvaluationResult, run_id: str = "") -> int | None:
    """Persist an evaluation result into episodic memory if available."""
    if memory is None:
        return None
    episodic = getattr(memory, "episodic", None)
    if episodic is None or not hasattr(episodic, "log"):
        return None
    summary = f"Eval {result.rubric} (score={result.score}): {result.feedback[:60]}"
    try:
        return episodic.log(
            kind="evaluation",
            summary=summary,
            detail=result.to_dict(),
            run_id=run_id,
        )
    except Exception as exc:  # noqa: BLE001  # episodic write is best effort
        log.warning("failed to log evaluation into episodic memory: %s", exc)
        return None


def get_recent_critiques(memory: Any, limit: int = 3) -> list[str]:
    """Retrieve recent failure feedback from episodic memory for prompt-level self-improvement."""
    if memory is None:
        return []
    episodic = getattr(memory, "episodic", None)
    if episodic is None or not hasattr(episodic, "recent"):
        return []
    try:
        entries = episodic.recent(limit=20, kind="evaluation")
        critiques: list[str] = []
        for e in entries:
            detail = e.get("detail") or {}
            if isinstance(detail, str):
                try:
                    detail = json.loads(detail)
                except (TypeError, ValueError):
                    detail = {}
            if not detail.get("passed", True) or float(detail.get("score", 1.0)) < 0.7:
                fb = detail.get("feedback")
                if fb and fb not in critiques:
                    critiques.append(fb)
            if len(critiques) >= limit:
                break
        return critiques
    except Exception as exc:  # noqa: BLE001  # critique fetch is best effort
        log.warning("failed to fetch recent critiques: %s", exc)
        return []


__all__ = [
    "EvaluationResult",
    "TaskEvaluator",
    "get_recent_critiques",
    "record_evaluation",
]
