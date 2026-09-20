"""goal capability: the session's durable goal — action get / set / status,
with the anti-self-continuation driver rules applied by actor (product rules
of the continuation driver, not permissions):

1. main-goal status: the agent reports done/blocked only; active/paused are
   the human's (arming the driver is a human decision);
2. main-goal text changes and clearing: human only (clearing the goal would
   otherwise dissolve the continuation target);
3. sub goals: the agent has full authority (pending/doing/done/blocked).

Boot downgrade (active -> paused) and the daily round budget stay unchanged.
"""

from __future__ import annotations

from typing import Any

from platform_capability import Registry, capability
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.master.goal import BLOCKED, DONE
from agent.runtime.current import current_session

_SUB_STATUSES = ("pending", "doing", "done", "blocked")
_AGENT_MAIN_STATUSES = (DONE, BLOCKED)
_HUMAN_MAIN_STATUSES = ("active", "paused", DONE, BLOCKED)


def goal_snapshot(goals: Any, session: str) -> dict:
    main = goals.get(session)
    subs = goals.subs(session)
    return {
        "session": session,
        "main": (
            {"text": main.text, "status": main.status, "rounds": main.rounds}
            if main is not None
            else None
        ),
        "subs": subs,
    }


def goal_action(
    goals: Any,
    *,
    action: str,
    session: str = "",
    scope: str = "main",
    text: str = "",
    status: str = "",
    index: int | None = None,
    _actor: ActorRef | None = None,
) -> dict:
    agent = _actor is not None and _actor.kind is ActorKind.AGENT

    def _require_user(reason: str) -> None:
        if agent:
            raise ServiceError(
                "agent",
                ErrorSuffix.FORBIDDEN,
                reason,
                hint="ask the user to make this change on the goal panel",
            )

    if action == "get":
        return goal_snapshot(goals, session)
    if action == "create":  # human convenience alias: set(scope=main)
        _require_user("arming a session goal is the user's decision")
        body = text.strip()
        if not body:
            raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "goal text must not be empty")
        goal = goals.create(session, body[:500])
        return {"session": session, "main": {"text": goal.text, "status": goal.status}}
    if action == "set":
        if scope == "main":
            _require_user("changing the main goal text is the user's decision")
            body = text.strip()
            if not body:
                goals.clear(session)
                return {"session": session, "cleared": True, **goal_snapshot(goals, session)}
            existing = goals.get(session)
            goal = (
                goals.create(session, body[:500])
                if existing is None
                else goals.set_text(session, body[:500])
            )
            return {"session": session, "main": {"text": goal.text, "status": goal.status}}
        if scope == "sub":
            subs = list(goals.subs(session))
            body = text.strip()
            if index is None:
                if not body:
                    raise ServiceError(
                        "agent", ErrorSuffix.INVALID_INPUT, "sub goal text must not be empty"
                    )
                subs.append({"text": body[:500], "status": "pending"})
            else:
                if index < 0 or index >= len(subs):
                    raise ServiceError("agent", ErrorSuffix.NOT_FOUND, f"no sub goal #{index}")
                if not body:
                    subs.pop(index)  # empty text deletes the entry
                else:
                    subs[index] = {
                        "text": body[:500],
                        "status": subs[index].get("status", "pending")
                        if isinstance(subs[index], dict)
                        else "pending",
                    }
            goals.set_subs(session, subs)
            return {"session": session, "subs": subs}
        raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, f"unknown scope: {scope!r}")
    if action == "status":
        if scope == "main":
            if not status:
                raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "status must not be empty")
            if agent and status not in _AGENT_MAIN_STATUSES:
                raise ServiceError(
                    "agent",
                    ErrorSuffix.FORBIDDEN,
                    "the agent may only report done/blocked for the main goal;"
                    " active/paused are the user's",
                )
            if not agent and status not in _HUMAN_MAIN_STATUSES:
                raise ServiceError(
                    "agent",
                    ErrorSuffix.INVALID_INPUT,
                    f"invalid main status: {status!r}",
                    hint="valid: active/paused/done/blocked",
                )
            goal = goals.set_status(session, status)
            if goal is None:
                raise ServiceError(
                    "agent", ErrorSuffix.NOT_FOUND, f"session has no goal: {session}"
                )
            return {"session": session, "main": {"text": goal.text, "status": goal.status}}
        if scope == "sub":
            if index is None or index < 0:
                raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "sub status needs index")
            subs = list(goals.subs(session))
            if index >= len(subs):
                raise ServiceError("agent", ErrorSuffix.NOT_FOUND, f"no sub goal #{index}")
            if status not in _SUB_STATUSES:
                raise ServiceError(
                    "agent",
                    ErrorSuffix.INVALID_INPUT,
                    f"invalid sub status: {status!r}",
                    hint="valid: pending/doing/done/blocked",
                )
            entry = subs[index] if isinstance(subs[index], dict) else {"text": subs[index]}
            entry["status"] = status
            subs[index] = entry
            goals.set_subs(session, subs)
            return {"session": session, "subs": subs}
        raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, f"unknown scope: {scope!r}")
    raise ServiceError(
        "agent",
        ErrorSuffix.INVALID_INPUT,
        f"unknown action: {action!r}",
        hint="valid actions: get/create/set/status",
    )


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="goal",
        description=(
            "Durable session goal: action get (snapshot {main, subs}) / set"
            " (scope=main text — human only; scope=sub with/without index —"
            " agent full authority, empty text deletes) / status (main:"
            " agent reports done/blocked only, human controls active/paused;"
            " sub: pending/doing/done/blocked)"
        ),
    )
    def goal(
        action: str,
        session_id: str = "",
        scope: str = "main",
        text: str = "",
        status: str = "",
        index: int | None = None,
        _actor: ActorRef | None = None,
    ) -> dict:
        assert deps.goal_manager is not None, "goal manager not wired at assembly"
        session = session_id or current_session()
        return goal_action(
            deps.goal_manager,
            action=action,
            session=session,
            scope=scope,
            text=text,
            status=status,
            index=index,
            _actor=_actor,
        )
