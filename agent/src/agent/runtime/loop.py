"""Event loop: take events -> dispatch -> act or stay silent.

On startup, events published while offline are first caught up via cursors before entering
the direct-push loop; handler exceptions are isolated and never break the loop (the event
stream is the only global facility, so its consumer must stay maximally conservative).

Exact subscription: subscribes only to the handler patterns plus extra_patterns (domain event
types declared by declarative hooks), never "*". Every event entering the loop is relayed to
hooks (with its own circuit breaker); without a relay this is a no-op.

Dynamic extras: the loop holds a runtime Subscription, and sync_extra_patterns converges the
declarative-hook domain event subscriptions to the current set (subscribe on approval,
unsubscribe on revocation, no restart). Handler domain bindings are immutable at runtime;
only the hook event-type layer changes.
"""

from __future__ import annotations

import fnmatch
import functools
import logging
from collections.abc import Awaitable, Callable, Iterable

from platform_contracts import Event
from platform_eventbus import CursorStore, EventBus, Subscription

from agent.runtime.recovery import CircuitBreaker, CircuitOpenError
from agent.runtime.trace import reset_current_trace, set_current_trace

Handler = Callable[[Event], Awaitable[None]]

log = logging.getLogger("agent.loop")


class EventLoop:
    def __init__(
        self,
        bus: EventBus,
        handlers: dict[str, Handler],
        *,
        cursors: CursorStore | None = None,
        subscriber: str = "agent.main",
        relay: Handler | None = None,
        extra_patterns: Iterable[str] = (),
    ) -> None:
        if "*" in handlers:
            raise ValueError('EventLoop handlers forbids "*": use relay for full forwarding')
        extra = tuple(extra_patterns)
        if "*" in extra:
            raise ValueError('EventLoop extra_patterns forbids "*": use relay for full forwarding')
        self._bus = bus
        self._handlers = handlers
        self._cursors = cursors
        self._subscriber = subscriber
        self._relay = relay
        self._relay_breaker = CircuitBreaker()  # own breaker isolates relay from domain handlers
        # Subscription patterns: deduped, order kept (handler keys + hook-declared event types)
        self._patterns = tuple(dict.fromkeys((*handlers.keys(), *extra)))
        self._stopped = False
        # Runtime subscription: held once run() assembles it; dynamic sync adds/removes its
        # patterns in place instead of resubscribing -> no subscription gap, no double
        # subscription; None before run() (sync only updates the snapshot)
        self._sub: Subscription | None = None
        # One breaker per pattern: after open_after consecutive failures of the same handler,
        # calls are skipped for reset_after; other patterns are unaffected and the loop
        # survives. Handlers are not wrapped in with_retry: retrying a handler
        # would dispatch events twice.
        self._breakers = {pattern: CircuitBreaker() for pattern in handlers}
        # Subscription epochs: (starting seq, pattern set) -- a pattern change takes effect
        # from the log tail at the moment of change and applies only to later events. Cursor
        # catch-up therefore knows exactly "what was subscribed at the time" and will not
        # replay events published before the subscription. Reset to the startup snapshot on
        # run().
        self._epochs: list[tuple[int, frozenset[str]]] = [(0, frozenset(self._patterns))]

    @property
    def patterns(self) -> tuple[str, ...]:
        """Currently subscribed patterns (direct push follows this tuple; catch-up
        judges each event by its subscription epoch)."""
        return self._patterns

    def _governing_patterns(self, seq: int) -> frozenset[str]:
        """Pattern set of the epoch the event seq belongs to (the latest epoch with start < seq)."""
        active = self._epochs[0][1]
        for start, patterns in self._epochs:
            if start < seq:
                active = patterns
            else:
                break
        return active

    def sync_extra_patterns(self, extra: Iterable[str]) -> None:
        """Converge hook domain event subscriptions to the given extras (at runtime).

        Idempotent diff: target = handlers + extra (deduped, order kept); compared with the
        current patterns, only the difference is added/removed. Handler domain bindings are
        always part of the target and never retracted. When started, mutates the runtime
        subscription's patterns in place (future events follow the new subscription) and opens
        a new epoch (bounded by the log tail, effective for later events only); before start,
        only the snapshot is updated and run() subscribes with the latest patterns. "*" is
        forbidden (same rule as in the constructor).
        """
        extra = tuple(extra)
        if "*" in extra:
            raise ValueError(
                'EventLoop dynamic subscription forbids "*": use relay for full forwarding'
            )
        target = tuple(dict.fromkeys((*self._handlers.keys(), *extra)))
        current = self._patterns
        if target == current:
            return
        if self._sub is not None:
            # Adds and removes match patterns exactly by string; target is a superset of the
            # handler keys, so any extra current pattern must belong to the extra layer, and
            # dropping it cannot touch domain bindings
            self._sub.add_patterns(*(p for p in target if p not in current))
            self._sub.drop_patterns(*(p for p in current if p not in target))
            self._epochs.append((self._bus.log.latest_seq(), frozenset(target)))
        else:
            # Not started: update the startup snapshot epoch (run() catches up with latest)
            self._epochs = [(0, frozenset(target))]
        self._patterns = target

    def stop(self) -> None:
        self._stopped = True

    async def _dispatch(self, event: Event) -> None:
        # Put the event trace into a ContextVar: capability calls within the chain
        # (packages/host/bridge) automatically join the same trace; reset after processing to avoid
        # polluting subsequent events in the loop task's context
        token = set_current_trace(event.trace_id) if event.trace_id else None
        try:
            for pattern, handler in self._handlers.items():
                if not fnmatch.fnmatchcase(event.type, pattern):
                    continue
                try:
                    await self._breakers[pattern].call(functools.partial(handler, event))
                except CircuitOpenError:
                    log.warning(
                        "handler circuit opened after consecutive failures, skipping temporarily: %s (event=%s)",
                        pattern,
                        event.type,
                    )
                except Exception:  # isolate event handling failures; the loop continues
                    log.exception("event handling failed: %s", event.type)
            relay = self._relay
            if relay is not None:
                # Every event entering the loop is relayed to hooks (the equivalent of the old
                # "*" handler); breaker/exception only skips the relay, never the domain
                # handlers already run above
                try:
                    await self._relay_breaker.call(lambda: relay(event))
                except CircuitOpenError:
                    log.warning(
                        "relay circuit opened after consecutive failures, skipping temporarily (event=%s)",
                        event.type,
                    )
                except Exception:  # isolate relay failures; the loop continues
                    log.exception("event relay failed: %s", event.type)
        finally:
            if token is not None:
                reset_current_trace(token)

    async def _process_pending(self) -> None:
        """Process unconsumed events from the log in seq order (paged), advancing the cursor
        per event.

        The direct-push queue is only a wake-up signal; processing always reads from the log:
        any events dropped while the queue was full are picked up by seq on the next wake-up,
        with no dedicated catch-up path needed.

        Type filtering happens on the consumer side using the event's subscription epoch (not
        SQL types): each event is judged by what its epoch subscribed to, so runtime pattern
        additions never retroactively match already-published events. Handler exceptions are
        isolated by _dispatch (logged and skipped) while the cursor advances as usual --
        replaying a failing handler would only fail again, so isolation-and-continue is the
        consumption policy, not event loss.
        """
        if self._cursors is None:
            return
        while True:
            rows = self._bus.log.read_after(after_seq=self._cursors.get(self._subscriber))
            if not rows:
                return
            for seq, event in rows:
                if any(fnmatch.fnmatchcase(event.type, p) for p in self._governing_patterns(seq)):
                    await self._dispatch(event)
                self._cursors.set(self._subscriber, seq)

    async def run(self) -> None:
        self._epochs = [(0, frozenset(self._patterns))]  # initial epoch: startup snapshot
        await self._process_pending()
        sub = self._bus.subscribe(*self._patterns)
        self._sub = sub
        while not self._stopped:
            event = await sub.get()
            if self._cursors is None:
                # cursor-less mode (tests / one-shot consumption): dispatch the event directly
                await self._dispatch(event)
            else:
                # cursor mode: the log is the source of truth; push-side gaps fill on next read
                await self._process_pending()
