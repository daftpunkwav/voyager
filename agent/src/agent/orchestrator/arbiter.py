"""Message arbitration: a new message arrives while a task is running.

Three modes (setting agent.arbiter.mode, default queue):
- queue: always queue; handled in order after the current turn finishes;
- auto: when the judge (short LLM call) deems the message related to the
  current task, merge it into context directly; otherwise queue;
- guide: judge says related -> merge; otherwise queue and prompt the user
  ("queued - want it handled first?").

Judge failures or degraded replies fall to the safe direction (always queue):
messages may be late, never lost.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from agent.llm import LLMClient
from agent.prompts import P, render

log = logging.getLogger("agent.arbiter")


class ArbiterMode(str, Enum):
    AUTO = "auto"
    QUEUE = "queue"
    GUIDE = "guide"


@dataclass(frozen=True)
class ArbiterDecision:
    action: str  # enqueue | merge | enqueue_notify
    reason: str


class Arbiter:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def decide(
        self, new_text: str, current_goal: str, *, mode: ArbiterMode = ArbiterMode.QUEUE
    ) -> ArbiterDecision:
        if mode is ArbiterMode.QUEUE:
            return ArbiterDecision("enqueue", "queue mode: finish the current task first")
        fallback = ArbiterDecision("enqueue", "judge unavailable, falling back to queue")
        try:
            reply = await self._llm.complete(
                [
                    {
                        "role": "system",
                        "content": render(
                            P.orchestrator.arbiter_judge, goal=current_goal, text=new_text
                        ),
                    }
                ]
            )
        except Exception:  # judge failure never loses a message: safe direction is queue
            log.exception("judge call failed, falling back to queue")
            return fallback
        if reply.degraded:
            return ArbiterDecision(
                "enqueue", "judge unavailable (quota degraded), falling back to queue"
            )
        verdict = (reply.text or "").strip().lower()
        related = verdict.startswith("merge")
        if related:
            return ArbiterDecision("merge", "related to the current task, merged into context")
        if mode is ArbiterMode.AUTO:
            return ArbiterDecision("enqueue", "new intent, queued")
        return ArbiterDecision(
            "enqueue_notify", "new intent, queued; say 'do this first' to handle it now"
        )
