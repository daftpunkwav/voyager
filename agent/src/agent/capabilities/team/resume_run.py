"""resume_run capability: rebuild a task instance from a checkpoint
(task-mode REACT); continue_run=true continues the ReAct round in the
background.

`resume_run()` is the one implementation; the capability and the agent's
resume_run tool both bind it. Background tasks are held in a module-level set
so the GC cannot drop them mid-run.
"""

from __future__ import annotations

import asyncio

from platform_capability import Registry, capability
from platform_contracts import DomainEvent

from agent.capabilities.deps import CapabilityDeps
from agent.runtime.state import CheckpointStore, RunStatus
from agent.subagent.spawn import Spawner

#: Task references for background resume runs (create_task results must be held,
#: otherwise the GC may reclaim the Task before completion and silently drop its
#: exception; same discipline as code_exec/_bg_tasks and master._bg)
_bg_tasks: set[asyncio.Task] = set()


async def resume_run(
    checkpoints: CheckpointStore, spawner: Spawner, run_id: str, continue_run: bool = False
) -> dict:
    """Rebuild the instance in memory (continue_run=false keeps it PAUSED
    for the UI to continue later); with continue_run=true, the whole ReAct
    round is continued in the background (same as dispatch_task: background,
    never blocks the caller).

    Background failure: exceptions are not swallowed — run_turn has already
    marked the instance FAILED and emitted RunFailed; here we additionally
    emit task.failed (with run_id/kind/error) through the existing failure
    card channel and write the error back to the on-disk checkpoint, so the
    UI list shows the failure instead of a ghost PAUSED entry.
    """
    inst = spawner.resume_from_checkpoint(run_id)
    out = {
        "resumed": inst.id,
        "run_id": run_id,
        "status": inst.status.value,
        "continuing": False,
    }
    if continue_run:

        async def _run() -> None:
            try:
                await spawner.start(inst)
            except asyncio.CancelledError:
                raise  # cancelled: AgentCancelled already emitted by cancel(); no FAILED write
            except Exception as exc:  # noqa: BLE001  # RunFailed sent; emit visible event
                err = f"{type(exc).__name__}: {exc}"
                # The instance owns its RuntimeEvents (AgentCancelled from cancel()
                # flows through the same stream). job_id=run_id: chatStore.taskKey
                # needs source_id/job_id to create a card; without it the card is
                # dropped and only a toast remains.
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
                    # task.failed is already out and user-visible; the disk write-back
                    # is best-effort — a second failure (file deleted / IO error) is
                    # not escalated further.
                    pass

        task = asyncio.create_task(_run())
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
        out["continuing"] = True
    return out


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="resume_run",
        description="Resume a task instance from a checkpoint (task-mode REACT; continue_run=true continues immediately)",
        cost=2,
    )
    async def _resume_run(run_id: str, continue_run: bool = False) -> dict:
        return await resume_run(deps.checkpoints, deps.spawner, run_id, continue_run)
