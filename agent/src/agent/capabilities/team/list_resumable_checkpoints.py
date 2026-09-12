"""list_resumable_checkpoints capability: checkpoints alive on disk that
carry a resume snapshot (pending resume or cleanup after a restart).

`list_resumable_checkpoints()` is the one implementation; the capability and
the agent's tool of the same name both bind it.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps
from agent.runtime.state import CheckpointStore, ResumeSnapshot


def list_resumable_checkpoints(checkpoints: CheckpointStore) -> dict:
    """Checkpoints alive on disk that carry a resume snapshot.

    The list covers alive items with a valid resume snapshot, partitioned
    by resumability:
    - resumable=True: mode=react and non-conversational; UI shows
      "continue + abandon";
    - resumable=False: conversational / non-react orphans; UI shows only
      "abandon" — these are entries mechanically marked PAUSED at boot but
      whose resume can never succeed; this list makes them visible so the
      user can clean them up (abandon accepts a wider set than the list).
    Corrupt/non-dict entries are skipped without exposing an entry point
    (same pattern as "bad files must not crash"); legacy entries without a
    snapshot were already marked failed at startup and are not alive.
    """
    items = []
    for st in checkpoints.list_alive():
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
                "resumable": resumable,  # False = abandon-only orphan
                "in_turn": bool(snap.in_turn),  # True = crashed mid-turn; resume continues there
            }
        )
    return {"items": items}


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="list_resumable_checkpoints",
        description="Resumable/abandonable task checkpoints (pending resume or cleanup after a process restart)",
    )
    def _list_resumable_checkpoints() -> dict:
        return list_resumable_checkpoints(deps.checkpoints)
