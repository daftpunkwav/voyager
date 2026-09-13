"""Subagent result synthesis for completion notices.

A dispatched task's full result can be tens of kilobytes; the chat timeline
notice used to blind-truncate it at 200 characters, which regularly cut off
exactly the conclusions the user needed. When the result is over the
threshold, one LLM call condenses it into a dense report (goal, key
findings, data worth keeping verbatim, open items); any failure (LLM error,
degraded reply, empty text) falls back to the truncation - a failed
synthesis must never lose the notification or crash the dispatch.
"""

from __future__ import annotations

import logging

from agent.llm import LLMClient

log = logging.getLogger("agent.master.synthesize")

#: Results at or below this length go out verbatim; longer ones get condensed
SYNTHESIZE_THRESHOLD = 400

#: Fallback cap when synthesis is unavailable (same shape as before, longer
#: than the old 200 so the head of the report still carries the conclusion)
FALLBACK_CHARS = 300

_PROMPT = (
    "【任务结果通报】下面是一个后台子任务{name}的完整结果。请把它压缩成一段"
    "不超过300字的通报,依次覆盖:任务是否完成;关键结论与产出;必须原样保留的"
    "关键数据/路径/命令;未完成事项。只输出通报正文,不要开场白:\n\n"
)


async def synthesize_result(llm: LLMClient, name: str, result: str) -> str:
    """Condense a long subagent result for the chat notice; short results and
    failed syntheses fall back to a capped excerpt."""
    result = str(result or "")
    if len(result) <= SYNTHESIZE_THRESHOLD:
        return result
    try:
        reply = await llm.complete(
            [{"role": "user", "content": _PROMPT.format(name=name) + result}]
        )
        text = (reply.text or "").strip()
        if text and not reply.degraded:
            return text
    except Exception:  # synthesis is best-effort; the notice must go out
        log.warning("result synthesis failed for %s; falling back", name, exc_info=True)
    return result[:FALLBACK_CHARS] + " …[已截断]"


__all__ = ["FALLBACK_CHARS", "SYNTHESIZE_THRESHOLD", "synthesize_result"]
