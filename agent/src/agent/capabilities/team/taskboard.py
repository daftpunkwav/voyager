"""taskboard capability: the team's publish / claim / confirm board.

One capability, human and agent callers share it (same implementation, two
drivers). publish opens a task (the host, after scoping it with the user);
claim raises a teammate's hand with an optional negotiation note (more info
needed / capacity concerns); confirm locks the claim and dispatches the run
in the background — execution lives in the agents panel, not the group
timeline; the completion path stamps the board and announces the delivery.
"""

from __future__ import annotations

from contextlib import suppress

from platform_capability import Registry, capability, current_chat_session
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.personas import TEAM_KEYS, canonical_persona_key
from agent.runtime.current import current_instance


def _current_persona() -> str:
    inst = current_instance.get()
    if inst is None:
        return ""
    # A member turn (@-mention / handoff) runs ON the chat instance, whose own
    # persona stays the host's ("orchestrator"): the speaking member's key is
    # carried beside it and wins, so a claim/publish inside a teammate's turn
    # attributes to the real speaker instead of Lucien.
    member = str(getattr(inst, "_member_persona", "") or "")
    if member:
        return member
    return str(getattr(inst, "persona", "") or "")


def _board_actor(explicit: str) -> str:
    """Caller identity for publish / claim / confirm: the executing turn's
    persona (the member key on a member turn), else the explicit argument for
    callers without a turn (REST / human UI). An agent caller naming a
    DIFFERENT identity is forging it — rejected, so a teammate cannot claim
    as a sibling member or confirm as the publisher and dispatch on its own.
    Empty on both sides = unresolved (callers keep their existing behavior:
    claim rejects, publish/confirm fall back to the orchestrator)."""
    actor = _current_persona()
    name = str(explicit or "").strip()
    if not name:
        return actor
    key = canonical_persona_key(name)
    if actor and key != actor:
        raise ServiceError(
            "agent",
            ErrorSuffix.FORBIDDEN,
            f"identity {name!r} does not match the calling persona",
            hint="omit the identity argument; it resolves from the executing turn",
        )
    return key


def _current_session() -> str:
    try:
        return str(current_chat_session.get() or "")
    except LookupError:  # REST/human path: no turn bound
        return ""


async def taskboard_action(
    deps: CapabilityDeps,
    *,
    action: str,
    task_id: str = "",
    title: str = "",
    brief: str = "",
    note: str = "",
    session: str = "",
    publisher: str = "",
    claimant: str = "",
    status: str = "",
) -> dict | list:
    board = deps.task_board
    if board is None:
        raise ServiceError("agent", ErrorSuffix.UNAVAILABLE, "no task board wired")
    if action == "list":
        return {"tasks": board.list(session=session or _current_session(), status=status)}
    if action == "publish":
        title_text = str(title or "").strip()
        brief_text = str(brief or "").strip()
        if not title_text or not brief_text:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                "publish needs title and brief (the task book: goal, constraints,"
                " expected deliverable)",
            )
        # The LLM passes display names ("Lucien"); identity is the structural
        # key ("orchestrator") — canonicalize whatever arrives, agent or REST.
        pub = _board_actor(publisher) or "orchestrator"
        sess = session or _current_session()
        if not sess:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                "publish needs a session (call it from a conversation turn or pass session)",
            )
        return board.publish(title=title_text, brief=brief_text, session=sess, publisher=pub)
    if action == "claim":
        if not task_id:
            raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "claim needs task_id")
        who = _board_actor(claimant)
        if not who or who not in TEAM_KEYS:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"claimant must be a resident teammate, not {who or claimant!r}",
                hint="resident teammates: iris/elio/miyai/atlas",
            )
        row = board.claim(task_id, claimant=who, note=str(note or ""))
        if deps.task_claim_notify is not None:
            await deps.task_claim_notify(row, who, str(note or ""))
        return row
    if action == "confirm":
        if not task_id:
            raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "confirm needs task_id")
        if deps.dispatch is None:
            raise ServiceError("agent", ErrorSuffix.UNAVAILABLE, "no dispatch wired for confirm")
        # The LLM passes display names ("Lucien"); identity is the structural
        # key ("orchestrator") — canonicalize whatever arrives, agent or REST.
        pub = _board_actor(publisher) or "orchestrator"
        locked = board.confirm(task_id, publisher=pub)
        claimant_key = str(locked.get("claimant") or "")
        brief_text = str(locked.get("brief") or "")
        if not claimant_key or not brief_text:
            board.reopen(task_id)
            raise ServiceError(
                "agent", ErrorSuffix.CONFLICT, f"task {task_id} lost its claim; reopened"
            )
        try:
            inst = await deps.dispatch(
                brief_text,
                persona=claimant_key,
                name=str(locked.get("title") or "")[:24],
                board_task_id=task_id,
            )
        except Exception:
            # A failed spawn must not strand the row in assigned (no exposed
            # action can recover it there): put the task back up, claim note
            # kept for context.
            with suppress(ServiceError):
                board.reopen(task_id)
            raise
        run_id = getattr(getattr(inst, "state", None), "run_id", "")
        if run_id and not hasattr(inst, "waiting_on"):  # DeferredDispatch has no state
            with suppress(ServiceError):
                board.mark_running(task_id, run_id=run_id)
        return {"task": board.get(task_id), "assigned_to": claimant_key, "run_id": run_id}

    raise ServiceError(
        "agent",
        ErrorSuffix.INVALID_INPUT,
        f"unknown action: {action!r}",
        hint="valid actions: publish/claim/confirm/list",
    )


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="taskboard",
        description=(
            "Team task board: action publish (title,brief — open a task for the"
            " team after scoping it with the user), claim (task_id,note — raise"
            " your hand; note carries negotiation: more info needed, capacity),"
            " confirm (task_id — the publisher locks the claim and dispatches"
            " the run in the background), list (session,status)"
        ),
    )
    async def taskboard(
        action: str,
        task_id: str = "",
        title: str = "",
        brief: str = "",
        note: str = "",
        session: str = "",
        publisher: str = "",
        claimant: str = "",
        status: str = "",
    ) -> dict | list:
        return await taskboard_action(
            deps,
            action=action,
            task_id=task_id,
            title=title,
            brief=brief,
            note=note,
            session=session,
            publisher=publisher,
            claimant=claimant,
            status=status,
        )
