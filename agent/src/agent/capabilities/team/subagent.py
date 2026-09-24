"""subagent capability: the whole subagent surface — spawn / list /
register / unregister / wait / send.

One capability, one action dispatch; the agent's subagent tool binds the same
capability (schema derived, audit symmetric).

- spawn runs the master's dispatch (assignment-time surface intersection
  narrows the child to the dispatcher's own tools);
- register validates agent-authored allowlists against the registering
  instance's surface (early readable feedback; dispatch re-checks anyway);
- send is wired to spawner.start(inst, message) but is guarded: today the
  only conversational instances are the user's own chat sessions (dispatched
  task instances are never conversational), and the agent must not drive the
  user's conversation — a send would inject a user-role message and trigger a
  full reply turn. Conversational instances are therefore refused, and react
  instances (never in WAITING_INPUT) get the readable conflict error. React
  follow-ups stay re-spawn with a goal referencing the board / prior
  conclusions.
"""

from __future__ import annotations

import asyncio
import logging

from platform_capability import Registry, capability, current_chat_session
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.personas import TEAM_KEYS, canonical_persona_key
from agent.runtime.current import current_instance as _current_instance
from agent.runtime.state import RunStatus
from agent.subagent.registry import SubagentDef, SubagentRegistry
from agent.subagent.spawn import Spawner
from agent.subagent.surface import surface_misses

log = logging.getLogger("agent.capabilities.subagent")

#: Held references so the GC cannot drop a background send mid-run
_send_tasks: set[asyncio.Task] = set()


def _release_send_task(task: asyncio.Task) -> None:
    """Done callback for fire-and-forget sends: drop the strong reference and
    retrieve the exception so a failed continuation is logged instead of
    surfacing only as a GC-time 'exception was never retrieved' warning (the
    run's own failure is already on its state / RUN_FAILED event)."""
    _send_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.warning("subagent send continuation failed: %s: %s", type(exc).__name__, exc)


_TERMINAL = frozenset({RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED})
_POLL_S = 0.5
_DEFAULT_TIMEOUT_S = 120.0
_MAX_TIMEOUT_S = 600.0


def _find(spawner: Spawner, id_or_name: str):
    for inst in spawner.instances.values():
        if id_or_name in (inst.id, inst.name):
            return inst
    return None


def _list_subagents(registry: SubagentRegistry, spawner: Spawner) -> dict:
    return {
        "definitions": [
            {
                "name": d.name,
                "mode": d.mode,
                "description": d.description,
                "persona": d.persona,
                "allowed_tools": list(d.allowed_tools) if d.allowed_tools else None,
                "max_rounds": d.max_rounds,
                "max_tool_calls": d.max_tool_calls,
                "network_mode": d.network_mode,
                "readonly": d.readonly,
                "enabled": d.enabled,
            }
            for d in registry.list()
        ],
        "running": [
            {
                "id": i.id,
                "run_id": i.state.run_id,
                "name": i.name,
                "status": i.status.value,
                "goal": i.task.goal,
                "started_ts": i.state.started_ts,
                "last_step": ((i.state.steps[-1].summary or "")[:120] if i.state.steps else ""),
                "depends_on": list(i.task.depends_on),
                "conversational": i.task.conversational,
                "session": i.task.session,
            }
            for i in spawner.instances.values()
            if i.status.alive
        ],
    }


async def _wait_subagent(
    spawner: Spawner, id_or_name: str, timeout_s: float = _DEFAULT_TIMEOUT_S
) -> dict:
    try:
        timeout = min(max(float(timeout_s), 0.1), _MAX_TIMEOUT_S)
    except (TypeError, ValueError):
        timeout = _DEFAULT_TIMEOUT_S
    inst = _find(spawner, id_or_name)
    if inst is None:
        raise ServiceError(
            "agent",
            ErrorSuffix.NOT_FOUND,
            f"no matching instance: {id_or_name}",
            hint="see subagent(action=list) for running instances",
        )
    deadline = asyncio.get_running_loop().time() + timeout
    while inst.status not in _TERMINAL and inst.status is not RunStatus.PAUSED:
        if asyncio.get_running_loop().time() >= deadline:
            return {
                "id": inst.id,
                "name": inst.name,
                "status": inst.status.value,
                "timed_out": True,
                "last_step": inst.last_step_summary(),
            }
        await asyncio.sleep(_POLL_S)
    return {
        "id": inst.id,
        "name": inst.name,
        "status": inst.status.value,
        "timed_out": False,
        "result": str(inst.state.result or ""),
        "error": str(inst.state.error or ""),
    }


async def subagent_action(
    deps: CapabilityDeps,
    *,
    action: str,
    goal: str = "",
    persona: str = "",
    mode: str = "",
    name: str = "",
    readonly: bool = False,
    allowed_tools: list[str] | None = None,
    id_or_name: str = "",
    message: str = "",
    timeout_s: float = _DEFAULT_TIMEOUT_S,
    description: str = "",
    max_rounds: int | None = None,
    max_tool_calls: int | None = None,
    network_mode: str = "",
    enabled: bool = True,
    _actor: ActorRef | None = None,
) -> dict | list:
    if allowed_tools is not None and not isinstance(allowed_tools, (list, tuple)):
        # Unmodeled capability: args pass through unvalidated, and a lenient
        # provider returning the array as a string would explode under
        # tuple("write") into per-character tool names, silently gutting the
        # spawned/registered surface
        raise ServiceError(
            "agent",
            ErrorSuffix.INVALID_INPUT,
            "allowed_tools must be a list of tool names",
        )
    if action == "spawn":
        if deps.dispatch is None:
            raise ServiceError("agent", ErrorSuffix.UNAVAILABLE, "no dispatch wired for spawn")
        if not goal.strip():
            raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "goal must not be empty")
        return await deps.dispatch(
            goal,
            persona=persona,
            mode=mode or None,
            name=name,
            readonly=bool(readonly),
            allowed_tools=tuple(allowed_tools) if allowed_tools else None,
        )
    if action == "list":
        return _list_subagents(deps.subagents, deps.spawner)
    if action == "register":
        # Assignment-surface validation (agent calls only): a definition
        # registered by a narrowed instance may not promise tools that
        # instance does not have. Dispatch re-checks anyway.
        if (
            allowed_tools
            and _actor is not None
            and _actor.kind is ActorKind.AGENT
            and (inst := _current_instance.get()) is not None
        ):
            missing = surface_misses(allowed_tools, inst.toolbelt.names())
            if missing:
                raise ServiceError(
                    "agent",
                    ErrorSuffix.FORBIDDEN,
                    f"tools not available on this instance's surface: {', '.join(missing)}",
                    hint="register an allowlist within this instance's own tools",
                )
        d = SubagentDef(
            name=name,
            description=description,
            mode=mode or "react",
            persona=persona,
            allowed_tools=tuple(allowed_tools) if allowed_tools else None,
            max_rounds=max_rounds,
            max_tool_calls=max_tool_calls,
            network_mode=network_mode,
            readonly=readonly,
            enabled=enabled,
        )
        deps.subagents.save(d)
        return {"name": d.name, "mode": d.mode, "allowed_tools": allowed_tools}
    if action == "unregister":
        deps.subagents.load(name)  # existence check: raises NOT_FOUND
        deps.subagents.delete(name)
        return {"deleted": name}
    if action == "wait":
        return await _wait_subagent(deps.spawner, id_or_name, timeout_s)
    if action == "send":
        inst = _find(deps.spawner, id_or_name)
        if inst is None:
            raise ServiceError(
                "agent",
                ErrorSuffix.NOT_FOUND,
                f"no matching instance: {id_or_name}",
                hint="see subagent(action=list) for running instances",
            )
        if getattr(inst.task, "conversational", False):
            # Interaction integrity: conversational instances are the user's
            # own chat sessions — a send would speak as the user and trigger
            # a full reply turn. The agent never drives them.
            raise ServiceError(
                "agent",
                ErrorSuffix.FORBIDDEN,
                f"{inst.name} is the user's chat instance; the agent cannot send it messages",
                hint="deliver conclusions via the board / a completion notice, or spawn a new task",
            )
        if inst.status is not RunStatus.WAITING_INPUT:
            raise ServiceError(
                "agent",
                ErrorSuffix.CONFLICT,
                f"instance {inst.name} is {inst.status.value}, not waiting for input",
                hint="task instances are not continued in place: spawn a new task"
                " with a goal referencing the board / prior conclusions",
            )
        text = str(message or "").strip()
        if not text:
            raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "message must not be empty")
        task = asyncio.create_task(deps.spawner.start(inst, text))
        _send_tasks.add(task)
        task.add_done_callback(_release_send_task)
        return {"sent": inst.id, "name": inst.name, "status": inst.status.value}
    if action == "handoff":
        # Team-room delegation: hand the floor to a resident teammate. The
        # member speaks a full turn once the current one ends, and its reply
        # lands in the shared timeline under their own name — no anonymous
        # spawned instance, no wait round-trip.
        if deps.team_handoff is None:
            raise ServiceError("agent", ErrorSuffix.UNAVAILABLE, "no team handoff wired")
        key = canonical_persona_key(persona.strip().lower())
        if key not in TEAM_KEYS or key == "orchestrator":
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"handoff targets a resident teammate, not {persona!r}",
                hint="resident teammates: iris (recon), elio (explainer), miyai (organizer), atlas (graph_guide)",
            )
        text = str(message or "").strip()
        if not text:
            raise ServiceError(
                "agent", ErrorSuffix.INVALID_INPUT, "message (the task brief) must not be empty"
            )
        try:
            session = str(current_chat_session.get() or "")
        except LookupError:  # background dispatch: no session bound
            session = ""
        if not session:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                "handoff needs the current chat session (call it from a conversation turn)",
            )
        out = await deps.team_handoff(session, key, text)
        return {**out, "action": "handoff"}
    raise ServiceError(
        "agent",
        ErrorSuffix.INVALID_INPUT,
        f"unknown action: {action!r}",
        hint="valid actions: spawn/list/register/unregister/wait/send/handoff",
    )


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="subagent",
        description=(
            "Subagent domain: action spawn (goal; persona/mode/name/readonly/"
            "allowed_tools — the allowlist may only narrow this instance's own"
            " surface), list, register (name/description/mode/allowed_tools/...),"
            " unregister (name), wait (id_or_name,timeout_s — blocks for the"
            " result), send (id_or_name,message — reserved continuation"
            " channel: the user's chat instances are refused and task"
            " instances are not continued in place, so prefer spawn)"
        ),
    )
    async def subagent(
        action: str,
        goal: str = "",
        persona: str = "",
        mode: str = "",
        name: str = "",
        readonly: bool = False,
        allowed_tools: list[str] | None = None,
        id_or_name: str = "",
        message: str = "",
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        description: str = "",
        max_rounds: int | None = None,
        max_tool_calls: int | None = None,
        network_mode: str = "",
        enabled: bool = True,
        _actor: ActorRef | None = None,
    ) -> dict | list:
        return await subagent_action(
            deps,
            action=action,
            goal=goal,
            persona=persona,
            mode=mode,
            name=name,
            readonly=readonly,
            allowed_tools=allowed_tools,
            id_or_name=id_or_name,
            message=message,
            timeout_s=timeout_s,
            description=description,
            max_rounds=max_rounds,
            max_tool_calls=max_tool_calls,
            network_mode=network_mode,
            enabled=enabled,
            _actor=_actor,
        )
