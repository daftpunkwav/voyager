"""Late-bound cross-domain capability calls for the composition root.

The composition root never imports a domain implementation to reach a
neighbor. Every cross-domain invocation goes through execute() so it rides
the same auth / quota / audit chain as REST and agent traffic.

call is the async entry (event-loop thread). call_sync is the worker-thread
twin used where no loop is running (e.g. asyncio.to_thread). The wirings
table is captured by reference so callers may be built before every domain
has been wired.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from platform_actor import ActorContext
from platform_capability import Wiring, execute
from platform_contracts import ActorKind, ActorRef

log = logging.getLogger("host.call")

#: Composition-root actor: SYSTEM plus wildcard scope so late-bound calls stay
#: legal if a capability later declares required scopes. Privilege lives here,
#: not as a special case inside LocalAuth.
HOST_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="host.call", scopes=("*",))

CallFn = Callable[[str, str, dict[str, Any]], Awaitable[Any]]
SyncCallFn = Callable[[str, str, dict[str, Any]], Any]


def _validate(domain: str, name: str, args: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(domain, str) or not domain.strip():
        raise RuntimeError("late-bound call domain must be a non-empty string")
    if not isinstance(name, str) or not name.strip():
        raise RuntimeError("late-bound call name must be a non-empty string")
    if args is None:
        return {}
    if not isinstance(args, dict):
        raise TypeError("late-bound call args must be a dict")
    return args


def bind_calls(
    wirings: Mapping[str, Wiring],
    *,
    actor: ActorRef = HOST_ACTOR,
    audit: Sequence[Any] | None = None,
    quota: Sequence[Any] | None = None,
) -> tuple[CallFn, SyncCallFn]:
    """Bind late-bound call / call_sync closures over a live wirings table.

    ``wirings`` is read at call time, not bind time: domains wired later are
    visible to earlier domains (graph L0 -> sources, ServiceLLM -> llm).
    """
    audit_hooks = list(audit or ())
    quota_hooks = list(quota or ())

    def _wiring_for(domain: str) -> Wiring:
        try:
            return wirings[domain]
        except KeyError:
            raise RuntimeError(
                f"late-bound call target domain is not wired: {domain!r} (wired: {sorted(wirings)})"
            ) from None

    async def call(domain: str, name: str, args: dict[str, Any] | None = None) -> Any:
        payload = _validate(domain, name, args)
        return await execute(
            _wiring_for(domain).registry,
            name,
            ActorContext(actor=actor),
            payload,
            audit=audit_hooks,
            quota=quota_hooks,
        )

    def call_sync(domain: str, name: str, args: dict[str, Any] | None = None) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(call(domain, name, args))
        raise RuntimeError(
            "call_sync must not be called on the event-loop thread: "
            "use async call, or run it in a worker thread"
        )

    log.debug("late-bound call closures bound (actor=%s)", actor.id)
    return call, call_sync
