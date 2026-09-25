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
from agent.prompts import P, render

log = logging.getLogger("agent.master.synthesize")

#: Results at or below this length go out verbatim; longer ones get condensed
SYNTHESIZE_THRESHOLD = 400

#: Fallback cap when synthesis is unavailable (same shape as before, longer
#: than the old 200 so the head of the report still carries the conclusion)
FALLBACK_CHARS = 300


async def synthesize_result(llm: LLMClient, name: str, result: str) -> str:
    """Condense a long subagent result for the chat notice; short results and
    failed syntheses fall back to a capped excerpt."""
    result = str(result or "")
    if len(result) <= SYNTHESIZE_THRESHOLD:
        return result
    try:
        reply = await llm.complete(
            [{"role": "user", "content": render(P.master.synthesize_result, name=name) + result}]
        )
        text = (reply.text or "").strip()
        if text and not reply.degraded:
            return text
    except Exception:  # synthesis is best-effort; the notice must go out
        log.warning("result synthesis failed for %s; falling back", name, exc_info=True)
    return result[:FALLBACK_CHARS] + " …[已截断]"


__all__ = ["FALLBACK_CHARS", "SYNTHESIZE_THRESHOLD", "synthesize_result"]
