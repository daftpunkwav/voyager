"""Health monitoring: probe registration, on-demand and periodic polling,
and service.health.changed events on status transitions.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from platform_contracts import (
    ActorKind,
    ActorRef,
    DomainEvent,
    Event,
    HealthReport,
    HealthStatus,
)
from platform_eventbus import EventBus

Probe = Callable[..., Any]  # () -> HealthReport | Awaitable[HealthReport]

_SYSTEM = ActorRef(kind=ActorKind.SYSTEM, id="platform.health")


class HealthMonitor:
    """Service health monitoring.

    Probes are transport-agnostic: they may hit an HTTP /health endpoint or
    run an in-process check.
    """

    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus = bus
        self._probes: dict[str, Probe] = {}
        self._last: dict[str, HealthReport] = {}
        self._task: asyncio.Task | None = None

    def register(self, service: str, probe: Probe) -> None:
        self._probes[service] = probe

    def unregister(self, service: str) -> None:
        self._probes.pop(service, None)
        self._last.pop(service, None)

    async def poll_once(self) -> dict[str, HealthReport]:
        """Run one polling round; publish service.health.changed on status
        transitions (including first observation)."""
        for name, probe in self._probes.items():
            try:
                report = probe()
                if inspect.isawaitable(report):
                    report = await report
            except Exception as exc:  # noqa: BLE001  # any probe failure means DOWN
                report = HealthReport(
                    service=name,
                    status=HealthStatus.DOWN,
                    detail=f"{type(exc).__name__}: {exc}",
                )
            prev = self._last.get(name)
            self._last[name] = report
            if self._bus is not None and (prev is None or prev.status != report.status):
                await self._bus.publish(
                    Event(
                        type=DomainEvent.SERVICE_HEALTH_CHANGED,
                        actor=_SYSTEM,
                        payload={
                            "service": name,
                            "from": prev.status.value if prev else HealthStatus.UNKNOWN.value,
                            "to": report.status.value,
                            "detail": report.detail,
                            "ts": report.ts,
                        },
                    )
                )
        return dict(self._last)

    def start(self, interval: float = 5.0) -> None:
        """Start background periodic polling (used by the gateway).

        Idempotent: repeated calls do not leak the previous task.
        """
        if self._task is not None and not self._task.done():
            return

        async def _run() -> None:
            while True:
                await self.poll_once()
                await asyncio.sleep(interval)

        self._task = asyncio.create_task(_run())

    async def stop(self) -> None:
        """Cancel and await the polling task (cleanup completes before this returns)."""
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def status(self, service: str) -> HealthStatus:
        report = self._last.get(service)
        return report.status if report else HealthStatus.UNKNOWN

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {name: report.to_dict() for name, report in self._last.items()}
