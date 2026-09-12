"""abandon_resumable_checkpoint capability: delete a resumable checkpoint
from disk and stop/remove its in-memory instance.

`abandon_resumable_checkpoint()` is the one implementation; the capability
and the agent's tool of the same name (L2 confirm, irreversible) both bind it.
"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.runtime.state import CheckpointStore, ResumeSnapshot
from agent.subagent.spawn import Spawner


async def abandon_resumable_checkpoint(
    checkpoints: CheckpointStore, spawner: Spawner, run_id: str
) -> dict:
    """Abandon a resumable checkpoint: delete from disk + clear the in-memory instance.

    The NOT_FOUND policy matches resume_run: rejects a missing file, a
    missing resume snapshot (legacy), or a corrupt snapshot. Any entry with
    a valid snapshot can be abandoned (wider than the resume list:
    conversational / non-react orphan checkpoints are not listed here, and
    this capability is their only cleanup path).
    The in-memory instance for the run: if alive, goes through
    spawner.cancel first (sets CANCELLED + interrupts the underlying task +
    emits AgentCancelled), then is removed from instances so it no longer
    appears in list_subagents.
    """
    try:
        state = checkpoints.load(run_id)
    except (FileNotFoundError, ValueError) as exc:
        raise ServiceError(
            "agent", ErrorSuffix.NOT_FOUND, f"checkpoint not found: {run_id}"
        ) from exc
    snap = None
    if isinstance(state.resume, dict):
        try:
            snap = ResumeSnapshot.from_dict(state.resume)
        except TypeError:
            snap = None
    if snap is None:
        raise ServiceError(
            "agent",
            ErrorSuffix.NOT_FOUND,
            f"checkpoint {run_id} has no resume snapshot (legacy) and cannot be abandoned",
        )
    hits = [inst.id for inst in spawner.instances.values() if inst.state.run_id == run_id]
    for inst_id in hits:
        inst = spawner.instances.get(inst_id)  # may be removed concurrently across awaits
        if inst is not None and inst.status.alive:
            await spawner.cancel(inst_id)
    for inst_id in hits:
        spawner.instances.pop(inst_id, None)
    checkpoints.delete(run_id)
    return {"abandoned": run_id}


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="abandon_resumable_checkpoint",
        description="Abandon a resumable checkpoint (deletes from disk; the in-memory instance is stopped and removed as well)",
        cost=1,
    )
    async def _abandon_resumable_checkpoint(run_id: str) -> dict:
        return await abandon_resumable_checkpoint(deps.checkpoints, deps.spawner, run_id)
