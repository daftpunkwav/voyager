"""Engine adapter: prefers the C engine, falls back to the
in-process Python engine, and emits an event on fallback.

Responsibilities:
- Users can force a mode via settings
  (graph.engine.mode = auto / c / python);
- The adapter shields both pipelines from engine differences
  (uniform call/health/index shape);
- A fallback is recorded once and published as the `graph.engine.fallback`
  event so the UI engine badge can show the degraded state.
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any, Protocol

from platform_contracts import ActorKind, ActorRef, DomainEvent, Event
from platform_eventbus import EventBus

from .c.client import CEngineClient

_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="graph.engine")


class Engine(Protocol):
    async def health(self) -> bool: ...
    async def call(self, name: str, args: dict[str, Any]) -> Any: ...
    async def index_repository(self, repo_path: str, **kw: Any) -> dict[str, Any]: ...


class _PythonEngineAdapter:
    """Wraps the in-process Python engine (synchronous call) in the same async shape as the C client."""

    flavor = "python"

    def __init__(self, data_root: Any) -> None:
        from .python.engine import GraphEngine

        self._engine = GraphEngine(data_root)

    async def health(self) -> bool:
        return bool(self._engine.health())

    async def call(self, name: str, args: dict[str, Any]) -> Any:
        # Search/export touch disk and CPU; must not block the event loop
        return await asyncio.to_thread(self._engine.call, name, args)

    async def index_repository(self, repo_path: str, **kw: Any) -> dict[str, Any]:
        return await asyncio.to_thread(
            partial(
                self._engine.index_repository,
                repo_path,
                mode=kw.get("mode", "moderate"),
                name=kw.get("name"),
            )
        )


class EngineAdapter:
    """Engine selection and fallback. resolve() is idempotent: each call probes according to settings."""

    def __init__(
        self,
        *,
        c_base_url: str,
        python_data_root: Any,
        bus: EventBus | None = None,
        mode: str = "auto",
    ) -> None:
        self._c = CEngineClient(c_base_url) if c_base_url else None
        self._python = _PythonEngineAdapter(python_data_root)
        self._bus = bus
        self._mode = mode  # auto | c | python

    async def resolve(self) -> tuple[Engine, str]:
        """Return (engine, engine name). auto: use C when healthy, otherwise fall back to Python and emit an event."""
        if self._mode == "python":
            return self._python, "python"
        if self._c is not None and await self._c.health():
            return self._c, "c"  # type: ignore[return-value]
        if self._mode == "c":
            from platform_contracts import ErrorSuffix, ServiceError

            raise ServiceError(
                "graph",
                ErrorSuffix.UNAVAILABLE,
                "C engine was forced but is unreachable",
                hint="check the sidecar process; or set graph.engine.mode to auto",
            )
        await self._emit(
            DomainEvent.GRAPH_ENGINE_FALLBACK,
            reason="C engine unreachable, fell back to the Python engine",
        )
        return self._python, "python"

    async def _emit(self, type_: str, **payload) -> None:
        if self._bus is not None:
            await self._bus.publish(Event(type=type_, actor=_ACTOR, payload=payload))
