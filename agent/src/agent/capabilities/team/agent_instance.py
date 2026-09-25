"""agent_instance capability: run control over subagent and main-conversation
instances — cancel / pause / resume / checkpoints / abandon.

cancel, pause and abandon accept id_or_name ("chat" = the chat main
instance); resume/checkpoints address on-disk checkpoints by run_id.
The agent's agent_instance tool binds this same capability.
"""

from __future__ import annotations

import asyncio
from typing import Any

from platform_capability import Registry, capability
from platform_contracts import DomainEvent, ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.engine.spawn import Spawner
from agent.runtime.state import ResumeSnapshot, RunStatus

#: Task references for the background resume run (create_task results must be
#: held, otherwise the GC may reclaim the Task before completion)
_bg_tasks: set[asyncio.Task] = set()


def _resolve(spawner: Spawner, chat: Any, id_or_name: str):
    if id_or_name == "chat":
        return chat
    return next(
        (i for i in spawner.instances.values() if i.id == id_or_name or i.name == id_or_name),
        None,
    )


async def agent_instance_action(
    deps: CapabilityDeps,
    *,
    action: str,
    id_or_name: str = "",
    run_id: str = "",
    continue_run: bool = False,
) -> dict:
    if action == "cancel":
        cancelled = await deps.spawner.cancel(id_or_name)
        if not cancelled:
            raise ServiceError(
                "agent",
                ErrorSuffix.NOT_FOUND,
                f"no matching running instance: {id_or_name}",
                hint="see subagent(action=list) for running instances",
            )
        return {"cancelled": cancelled}
    if action == "pause":
        chat = deps.sessions.instance_for(deps.sessions.active_id())
        inst = _resolve(deps.spawner, chat, id_or_name)
        if inst is None:
            raise ServiceError(
                "agent",
                ErrorSuffix.NOT_FOUND,
                f"no matching instance: {id_or_name}",
                hint="see subagent(action=list) for running instances",
            )
        if inst.status.value in ("completed", "failed", "cancelled"):
            raise ServiceError(
                "agent",
                ErrorSuffix.CONFLICT,
                f"instance {inst.name} is {inst.status.value}, cannot pause",
            )
        inst.pause_requested = True
        return {"pausing": inst.id, "name": inst.name, "status": "pause-requested"}
    if action == "resume":
        inst = deps.spawner.resume_from_checkpoint(run_id)
        out = {
            "resumed": inst.id,
            "run_id": run_id,
            "status": inst.status.value,
            "continuing": False,
        }
        if continue_run:
            checkpoints = deps.checkpoints

            async def _run() -> None:
                try:
                    await deps.spawner.start(inst)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001  # RunFailed sent; emit visible event
                    err = f"{type(exc).__name__}: {exc}"
                    await inst.events.emit(
                        DomainEvent.TASK_FAILED,
                        run_id=run_id,
                        job_id=run_id,
                        kind="resume",
                        title=inst.name,
                        error=err[:300],
                    )
                    try:
                        state = checkpoints.load(run_id)
                        state.status = RunStatus.FAILED
                        state.error = err
                        checkpoints.save(state)
                    except Exception:  # noqa: BLE001, S110
                        pass

            task = asyncio.create_task(_run())
            _bg_tasks.add(task)
            task.add_done_callback(_bg_tasks.discard)
            out["continuing"] = True
        return out
    if action == "checkpoints":
        items = []
        for st in deps.checkpoints.list_alive():
            raw = st.resume
            if not isinstance(raw, dict):
                continue
            try:
                snap = ResumeSnapshot.from_dict(raw)
            except TypeError:
                continue
            resumable = snap.mode == "react" and not snap.conversational
            items.append(
                {
                    "run_id": st.run_id,
                    "status": st.status.value,
                    "goal": snap.goal or st.task,
                    "instance_name": snap.instance_name,
                    "started_ts": st.started_ts,
                    "last_step": (st.steps[-1].summary or "")[:120] if st.steps else "",
                    "mode": snap.mode,
                    "conversational": snap.conversational,
                    "resumable": resumable,
                    "in_turn": bool(snap.in_turn),
                }
            )
        return {"items": items}
    if action == "abandon":
        checkpoints = deps.checkpoints
        try:
            state = checkpoints.load(run_id)
        except (FileNotFoundError, ValueError) as exc:
            raise ServiceError(
                "agent", ErrorSuffix.NOT_FOUND, f"checkpoint not found: {run_id}"
            ) from exc
        asnap: ResumeSnapshot | None = None
        if isinstance(state.resume, dict):
            try:
                asnap = ResumeSnapshot.from_dict(state.resume)
            except TypeError:
                asnap = None
        if asnap is None:
            raise ServiceError(
                "agent",
                ErrorSuffix.NOT_FOUND,
                f"checkpoint {run_id} has no resume snapshot (legacy) and cannot be abandoned",
            )
        hits = [i.id for i in deps.spawner.instances.values() if i.state.run_id == run_id]
        for inst_id in hits:
            inst = deps.spawner.instances.get(inst_id)
            if inst is not None and inst.status.alive:
                await deps.spawner.cancel(inst_id)
        for inst_id in hits:
            deps.spawner.instances.pop(inst_id, None)
        checkpoints.delete(run_id)
        return {"abandoned": run_id}
    raise ServiceError(
        "agent",
        ErrorSuffix.INVALID_INPUT,
        f"unknown action: {action!r}",
        hint="valid actions: cancel/pause/resume/checkpoints/abandon",
    )


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="agent_instance",
        description=(
            "Run control: action cancel (id_or_name; 'chat' = the chat main"
            " instance), pause (cooperative, next step boundary), resume"
            " (run_id, continue_run), checkpoints (resumable/abandonable list),"
            " abandon (run_id — deletes the checkpoint, irreversible)"
        ),
    )
    async def agent_instance(
        action: str, id_or_name: str = "", run_id: str = "", continue_run: bool = False
    ) -> dict:
        return await agent_instance_action(
            deps, action=action, id_or_name=id_or_name, run_id=run_id, continue_run=continue_run
        )
