"""Question broker: publishes agent.ask events and resolves the pending
Future when the user's answer arrives (the mechanism behind the ask_user tool
and the answer_question capability).

The frontend (widgets/chat/AskDialog.tsx) subscribes to agent.ask events and
renders the dialog; the gateway posts the user's answer back to
AskUser.answer.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

from platform_contracts import DomainEvent, Event
from platform_eventbus import EventBus

from agent.runtime.events import AGENT_MAIN

AGENT_ASK = DomainEvent.AGENT_ASK  # compat alias; canonical name in platform_contracts.DomainEvent


@dataclass(frozen=True)
class Question:
    prompt: str
    kind: str = "confirm"  # confirm | choice | multi_choice | slider | rating | text
    options: tuple[str, ...] = ()  # per-kind count bounds (choice/multi 2-8, slider 1-8)
    min: float | None = None
    max: float | None = None
    timeout_s: float = 120.0


class AskUser:
    def __init__(self, bus: EventBus | None, *, actor=AGENT_MAIN) -> None:
        self._bus = bus
        self._actor = actor
        self._pending: dict[str, asyncio.Future] = {}

    async def ask(self, q: Question, *, trace_id: str = "") -> Any:
        """Publish the question and wait for the answer; returns None on timeout
        (the caller decides whether to continue or give up)."""
        qid = uuid.uuid4().hex[:12]
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[qid] = fut
        if self._bus is not None:
            await self._bus.publish(
                Event(
                    type=AGENT_ASK,
                    actor=self._actor,
                    trace_id=trace_id,
                    payload={
                        "question_id": qid,
                        "prompt": q.prompt,
                        "kind": q.kind,
                        "options": list(q.options),
                        "min": q.min,
                        "max": q.max,
                    },
                )
            )
        try:
            return await asyncio.wait_for(fut, q.timeout_s)
        except TimeoutError:
            return None
        finally:
            self._pending.pop(qid, None)

    def answer(self, question_id: str, value: Any) -> bool:
        """Entry point for user answers. Returns whether a pending question matched."""
        fut = self._pending.get(question_id)
        if fut is not None and not fut.done():
            fut.set_result(value)
            return True
        return False

    @property
    def pending_count(self) -> int:
        return len(self._pending)


__all__ = ["AGENT_ASK", "AskUser", "Question"]
