"""Event loop wiring table: domain handler bindings and the hook relay.

Provides data and the relay only, no assembly: EventLoop(...) is still constructed by
build_agent, with cursors / subscriber defaults left to the assembly root. Components are
referenced by duck typing and no ABCs are introduced; this module must not import
build_agent / AgentApp.
"""

from __future__ import annotations

from platform_contracts import DomainEvent

from agent.runtime.loop import Handler

__all__ = ["bind_event_loop"]


def bind_event_loop(
    master, hooks, *, trajectory=None, proactive=None, trigger_handler=None, trigger_patterns=()
):
    """Return (handlers, relay, extra_patterns) for build_agent to pass to EventLoop.

    - handlers: the domain bindings (frozen);
    - relay: every event entering the loop is forwarded to on_event (independent breaker
      lives on the EventLoop side);
    - extra_patterns: domain event types declared by declarative hooks, used to make the
      subscription exact;
    - trajectory: optional TrajectoryStore; every agent.step event nudges its catch-up
      (the store reads the log from its own cursor, so this is a trigger, not the data).
    """
    handlers: dict[str, Handler] = {
        DomainEvent.USER_MESSAGE: lambda ev: master.handle_user_message(
            ev.payload.get("content", ""),
            trace_id=ev.trace_id,
            # Target chat session; empty -> the user's active session
            session_id=str(ev.payload.get("session") or ""),
        ),
    }
    if trajectory is not None:
        # Inline on the loop thread: the fold is microsecond-scale sqlite work,
        # and a worker thread would race the log's close at shutdown
        async def _project(_ev):
            trajectory.catch_up()

        handlers[DomainEvent.AGENT_STEP] = _project
    if proactive is not None:
        handlers[DomainEvent.USER_ONLINE] = proactive.on_user_online
    if trigger_handler is not None:
        for pattern in trigger_patterns:
            handlers[pattern] = trigger_handler

    # Domain events -> hooks: the on_event filter matches event types itself;
    # with no hooks this is an empty fire (no more borrowing "*" to subscribe to everything)
    async def relay(ev):
        await hooks.fire("on_event", event=ev)

    return handlers, relay, hooks.event_patterns
