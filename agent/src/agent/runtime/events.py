"""Runtime-level event emission (RuntimeEvent): events carry run/subagent
context into the event stream.
"""

from __future__ import annotations

from typing import Any

from platform_contracts import ActorKind, ActorRef, Event, RuntimeEvent
from platform_eventbus import EventBus

AGENT_MAIN = ActorRef(kind=ActorKind.AGENT, id="agent.main")


class RuntimeEvents:
    def __init__(self, bus: EventBus | None, actor: ActorRef = AGENT_MAIN) -> None:
        self._bus = bus
        self._actor = actor

    async def emit(self, type_: str, *, trace_id: str = "", **payload: Any) -> None:
        if self._bus is not None:
            await self._bus.publish(
                Event(type=type_, actor=self._actor, payload=payload, trace_id=trace_id)
            )


__all__ = ["AGENT_MAIN", "RuntimeEvent", "RuntimeEvents"]
