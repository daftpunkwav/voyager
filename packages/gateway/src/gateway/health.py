"""Health probing: periodically and passively probes mounted packages.

The gateway only holds a health snapshot (the only state it is allowed to
keep); a status transition publishes service.health.changed. Probe
functions are injected by the deployment entry point (direct in-process
health calls in the monolith; HTTP GET /health in a microservice setup).
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable

from platform_contracts import ActorKind, ActorRef, DomainEvent, Event, HealthStatus
from platform_eventbus import EventBus

ProbeFn = Callable[[], dict | Awaitable[dict]]
_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="gateway.health")


class HealthProbe:
    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus = bus
        self._probes: dict[str, ProbeFn] = {}
        # domain -> {"status": str, "detail": dict, "ts": float}
        self._snapshot: dict[str, dict] = {}

    def register(self, domain: str, probe: ProbeFn) -> None:
        self._probes[domain] = probe

    async def probe(self, domain: str) -> dict:
        """Probe a single service; any exception maps to down (isolated, never raised)."""
        fn = self._probes[domain]
        try:
            out = fn()
            report = await out if inspect.isawaitable(out) else out
            status = str(report.get("status", HealthStatus.UP.value))
        except Exception as exc:  # noqa: BLE001 probes never take gateway down (isolation)
            report = {"error": f"{type(exc).__name__}: {exc}"}
            status = HealthStatus.DOWN.value
        await self._record(domain, status, report)
        return self._snapshot[domain]

    async def probe_all(self) -> dict[str, dict]:
        for domain in self._probes:
            await self.probe(domain)
        return dict(self._snapshot)

    async def _record(self, domain: str, status: str, detail: dict) -> None:
        prev = self._snapshot.get(domain, {}).get("status")
        self._snapshot[domain] = {"status": status, "detail": detail, "ts": time.time()}
        if prev is not None and prev != status and self._bus is not None:
            await self._bus.publish(
                Event(
                    type=DomainEvent.SERVICE_HEALTH_CHANGED,
                    actor=_ACTOR,
                    payload={"service": domain, "from": prev, "to": status},
                )
            )

    def snapshot(self) -> dict[str, dict]:
        return dict(self._snapshot)

    def overall(self) -> str:
        if any(s["status"] == HealthStatus.DOWN.value for s in self._snapshot.values()):
            return HealthStatus.DEGRADED.value
        return HealthStatus.UP.value
