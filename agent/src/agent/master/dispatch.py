"""Task dispatch: Master's dispatch logic extracted into its own module.

Only assembles the TaskBook per persona / mode / tools / network tier,
starts the subagent in the background, and routes completion/failure back
into the message stream via the public master.reply.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass

from platform_contracts import ErrorSuffix, ServiceError

from agent.contracts import DispatchMaster, SettingsReader
from agent.master.synthesize import synthesize_result
from agent.master.task_graph import DeferredTask  # noqa: F401  # re-exported type
from agent.personas import resolve_persona
from agent.policy import NetworkPolicy, PolicyEngine, narrow_network
from agent.runtime.current import current_instance
from agent.runtime.state import RunStatus
from agent.settings import SUBAGENTS_MAX_DEPTH_KEY
from agent.subagent import Mode, Spawner, SubagentInstance, TaskBook
from agent.subagent.limits import limits_from_settings
from agent.subagent.registry import SubagentDef, SubagentRegistry
from agent.subagent.surface import intersect_surface, surface_misses
from agent.tools.core.base import Toolbelt


def _turn_degraded(inst) -> bool:
    """Whether the run's final LLM round was harness degradation text (quota /
    provider failure placeholder) rather than model output — such a delivery
    is a failure, not a fake completion. Read back from the step trail.

    Same check as subagent.turn._turn_degraded (this copy is duck-typed so a
    fake instance without a steps trail reads as not degraded)."""
    for step in reversed(getattr(inst.state, "steps", ())):
        if step.kind == "llm":
            return bool((step.detail or {}).get("degraded"))
    return False


log = logging.getLogger("agent.dispatch")


async def dispatch_task(
    master: DispatchMaster,
    spawner: Spawner,
    settings: SettingsReader,
    policy: PolicyEngine | None,
    subagents: SubagentRegistry | None,
    hooks,
    goal: str,
    *,
    persona: str = "",
    mode: str | None = None,
    allowed_tools: tuple[str, ...] | None = None,
    readonly: bool = False,
    name: str = "",
    constraints: str = "",
    depends_on: tuple[str, ...] | None = None,
    board_task_id: str = "",
) -> SubagentInstance | DeferredDispatch:
    """Dispatch implementation.

    Personas resolve against built-in presets first; on a miss, the
    user-defined subagent registry is consulted (isomorphic to presets for
    the master: its mode and allowed_tools whitelist apply).

    Surface resolution narrows only, never widens, except for one explicit
    caller choice: an explicit allowed_tools list takes precedence over a
    custom definition or preset template (the caller names exactly what it
    wants). readonly then drops every write/irreversible tool from whatever
    surface results and can never be widened back, so a review task never
    carries write tools even if a preset later gains one.
    """

    task_name = name or goal[:16]
    graph = getattr(master, "task_graph", None)
    if graph is not None and depends_on:
        outstanding = graph.pending(task_name, depends_on=tuple(depends_on))
        if outstanding:
            graph.stash_args(
                task_name,
                {
                    "goal": goal,
                    "persona": persona,
                    "mode": mode,
                    "allowed_tools": allowed_tools,
                    "readonly": readonly,
                    "name": name,
                    "constraints": constraints,
                    "depends_on": None,
                },
            )
            waiting = ", ".join(sorted(outstanding))
            await master.reply(
                f"[queued] {task_name}: waits for {waiting}", session=_origin_session(master)
            )
            return DeferredDispatch(name=task_name, waiting_on=tuple(sorted(outstanding)))

    preset = resolve_persona(persona) if persona else None
    custom = _load_custom(subagents, persona) if persona and preset is None else None
    # Caller-named allowlist (the spawn parameter): authored at call time by
    # the model, so out-of-surface entries are its own mistake and get a
    # rejection it can correct. Curated lists (custom definitions, persona
    # presets) intersect silently — a preset may enumerate bridge tools of a
    # domain that is simply not mounted in this app.
    explicit_tools = allowed_tools is not None
    if custom is not None and not custom.enabled:
        raise ServiceError(
            "agent",
            ErrorSuffix.FORBIDDEN,
            f"subagent {persona} is disabled",
            hint="re-enable it in settings (register_subagent enabled=true) before dispatching",
        )
    if custom is not None:
        if mode is None:
            mode = custom.mode
        if allowed_tools is None:
            allowed_tools = custom.allowed_tools
        readonly = readonly or custom.readonly
        constraints = f"{constraints}\n{custom.description}".strip()
    elif preset is not None and preset.key == "orchestrator":
        mode = Mode.REACT.value  # the orchestrator is forced to ReAct
    if allowed_tools is None and preset is not None:
        allowed_tools = preset.tool_allow
    limits = limits_from_settings(
        settings,
        max_rounds=custom.max_rounds if custom is not None else None,
        max_tool_calls=custom.max_tool_calls if custom is not None else None,
    )
    try:
        plan_mode = Mode(mode) if mode else None
    except ValueError:
        # Fail loud with an actionable error instead of a bare ValueError that
        # surfaces as "[工具失败] ValueError: ..." downstream
        valid = ", ".join(m.value for m in Mode)
        raise ServiceError(
            "agent",
            ErrorSuffix.INVALID_INPUT,
            f"unknown mode: {mode!r}",
            hint=f"valid modes: {valid}",
        ) from None
    # Delegation depth (monotonic): one level under the dispatching instance;
    # resumed instances keep their persisted depth, so a restored subagent
    # cannot restart counting from zero and escape the recursion cap
    parent = current_instance.get()
    depth = (parent.state.delegation_depth + 1) if parent is not None else 1
    try:
        max_depth = int(settings.get(SUBAGENTS_MAX_DEPTH_KEY))
    except (TypeError, ValueError, ServiceError):
        max_depth = 3
    if depth > max_depth:
        raise ServiceError(
            "agent",
            ErrorSuffix.FORBIDDEN,
            f"delegation depth {depth} exceeds the limit ({max_depth})",
            hint="flatten the task plan or ask the user to raise agent.subagents.max_depth",
        )
    # Assignment-time surface intersection (monotone narrowing): a dispatch
    # from inside a live instance can never grant a wider surface than the
    # dispatcher itself has. Caller-named entries are validated first —
    # anything this instance cannot offer is a readable rejection so the
    # model corrects its own request — then every allowlist is frozen to the
    # intersection, so a later checkpoint resume rebuilds the same narrowed
    # surface instead of widening back to the root roster. A parent without
    # a readable toolbelt (test fakes) imposes no constraint.
    parent_belt = getattr(parent, "toolbelt", None) if parent is not None else None
    if parent_belt is not None:
        parent_names: list[str] = parent_belt.names()
        if allowed_tools is not None:
            if explicit_tools:
                missing = surface_misses(allowed_tools, parent_names)
                if missing:
                    raise ServiceError(
                        "agent",
                        ErrorSuffix.FORBIDDEN,
                        f"tools not available on this instance's surface: {', '.join(missing)}",
                        hint=(
                            "dispatch with tools this instance actually has, "
                            "or omit allowed_tools to inherit its surface"
                        ),
                    )
            allowed_tools = intersect_surface(allowed_tools, parent_names)
        else:
            allowed_tools = tuple(parent_names)
    task = TaskBook(
        goal=goal,
        constraints=constraints,
        depends_on=tuple(depends_on or ()),
        board_task_id=board_task_id,
        mode=plan_mode,
        allowed_tools=allowed_tools,
        readonly=readonly,
        limits=limits,
        # The dispatching session owns the result: the chat instance running
        # when spawn_subagent fired (fallback: the active session), so task
        # results route back to that session's timeline
        session=_origin_session(master),
    )
    spawn_key = preset.key if preset is not None else persona
    log.info(
        "dispatch task name=%s persona=%s mode=%s readonly=%s tools=%s",
        name or goal[:16],
        spawn_key or "-",
        mode or "-",
        readonly,
        len(allowed_tools) if allowed_tools is not None else "full",
    )
    inst = spawner.spawn(task, persona=spawn_key, name=name or goal[:16])
    # Parent linkage for the cancel cascade: the spawn_subagent tool runs
    # inside the dispatching instance's turn, where current_instance is set;
    # a background dispatch (goal/queue) has no turn context and stays top-level
    _parent = current_instance.get(None)
    _parent_id = getattr(_parent, "id", "") if _parent is not None else ""
    if _parent_id and _parent_id != inst.id:
        inst.parent_run_id = _parent_id
    inst.state.delegation_depth = depth
    if custom is not None and custom.network_mode:
        inst.rebind_toolbelt(
            _narrowed_toolbelt(inst.toolbelt, custom.network_mode, settings, policy)
        )
    master.digests.upsert(inst)
    if hooks is not None:
        await hooks.fire("on_subagent_start", subagent=inst.id, goal=goal)

    async def _run() -> None:
        try:
            result = await spawner.start(inst)
        except asyncio.CancelledError:
            # Cancellation always propagates through spawner.start (the task
            # itself is interrupted), so the else branch below is unreachable
            # for it: the [cancelled] notice lives here, before the re-raise.
            # Best effort - shutdown may already be tearing the channel down.
            if inst.status is RunStatus.CANCELLED:
                with suppress(Exception):
                    if getattr(inst.task, "board_task_id", ""):
                        # The board row must not linger as running: a cancelled
                        # board-backed run closes out through the same failure
                        # card + relay path as any other board outcome.
                        await master.announce_delivery(inst, ok=False, result="", error="cancelled")
                    else:
                        await master.reply(
                            f"[cancelled] {inst.name}", session=inst.task.session, kind="notice"
                        )
            raise
        except Exception as exc:  # run_turn already recorded the state; notify + server-side log
            log.exception("background dispatch failed: %s", inst.name)
            # A board-backed run announces a failure card + the host's relay;
            # plain dispatches keep the lightweight [failed] notice
            if getattr(inst.task, "board_task_id", ""):
                await master.announce_delivery(
                    inst, ok=False, result="", error=f"{type(exc).__name__}: {exc}"
                )
            else:
                await master.reply(
                    f"[failed] {inst.name}: {type(exc).__name__}: {exc}",
                    session=inst.task.session,
                    kind="notice",
                )
        else:
            if inst.status is RunStatus.CANCELLED:
                # reachable when the instance was cancelled while still queued
                # for a concurrency slot: start() returns normally (no
                # CancelledError) but nothing ran
                if getattr(inst.task, "board_task_id", ""):
                    await master.announce_delivery(inst, ok=False, result="", error="cancelled")
                else:
                    await master.reply(f"[cancelled] {inst.name}", session=inst.task.session)
            elif inst.status.value == "paused":
                await master.reply(
                    f"[paused] {inst.name}", session=inst.task.session, kind="notice"
                )
            elif getattr(inst.task, "board_task_id", ""):
                # Team task-board delivery: structured card + the standing
                # host relays the report to the user (event-driven wakeup,
                # not a sleep loop). A degraded turn's text is harness
                # placeholder, not a real answer — announce it as a failure.
                ok = inst.status is RunStatus.COMPLETED and not _turn_degraded(inst)
                await master.announce_delivery(
                    inst, ok=ok, result=result if ok else "", error="" if ok else result[:500]
                )
            else:
                # Long results get one synthesis call so the notice carries the
                # conclusions instead of a blind cut; failures fall back inside
                summary = await synthesize_result(master.llm, inst.name, result)
                await master.reply(
                    f"[done] {inst.name}: {summary}", session=inst.task.session, kind="notice"
                )
        finally:
            master.digests.upsert(inst)
            # Join point: a finished (or failed) task releases / blocks the
            # deferred tasks waiting on it (deterministic either way)
            master.finish_task(inst.name, ok=inst.status is RunStatus.COMPLETED)
            if hooks is not None:
                await hooks.fire("on_subagent_end", subagent=inst.id)

    task_handle = asyncio.create_task(_run())
    master.track_background(task_handle)
    return inst


@dataclass(frozen=True)
class DeferredDispatch:
    """Duck-types the SubagentInstance surface spawn_subagent reads (id /
    name / status) for a task held back by unresolved dependencies."""

    name: str
    waiting_on: tuple[str, ...]
    id: str = ""
    status: str = "deferred"


def _load_custom(subagents: SubagentRegistry | None, name: str) -> SubagentDef | None:
    """Fetch a user-defined subagent definition by name; None when unregistered
    (treated as an ordinary unnamed task)."""
    from platform_contracts import ServiceError

    if subagents is None:
        return None
    try:
        return subagents.load(name)
    except ServiceError:
        return None


def _origin_session(master: DispatchMaster) -> str:
    """Session owning this dispatch: the instance whose turn is executing
    (spawn_subagent runs mid-turn), else the user's active session."""
    running = current_instance.get()
    session = getattr(running, "session", None) if running is not None else None
    if session:
        return session
    return master.sessions.active_id()


def _narrowed_toolbelt(
    belt: Toolbelt,
    requested_mode: str,
    settings: SettingsReader,
    policy: PolicyEngine | None,
) -> Toolbelt:
    """Instance-specific toolbelt when a user-defined subagent requests a
    network tier ("dispatch first, then narrow; only ever stricter").

    The same (already trimmed) tool table with a fresh PolicyEngine: fs/app
    reuse the global policy, the network tier comes from narrow_network
    (global, custom), and domains come from the global agent.network.domains.
    The copy carries no settings handle - a global loosening mid-task never
    flows back into an already dispatched instance.
    """
    global_mode = str(settings.get("agent.network.mode") or "")
    domains = tuple(settings.get("agent.network.domains") or ())
    engine = PolicyEngine(
        network=NetworkPolicy(mode=narrow_network(global_mode, requested_mode), domains=domains),
        fs=policy.fs if policy is not None else None,
        app=policy.app if policy is not None else None,
    )
    return belt.with_policy(engine)
