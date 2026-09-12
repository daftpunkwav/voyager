"""Batch note actions: archive/unarchive/delete/export/pin/unpin.

Responsibilities:
- Apply one action (archive / unarchive / delete / export / pin / unpin) to
  up to 100 note ids in a single call
- Deduplicate ids and record per-note failures in `failed`; one failure
  does not abort the rest
"""

from __future__ import annotations

from platform_capability import capability
from platform_contracts import ErrorSuffix, ServiceError

from .lifecycle import delete_note, update_note
from .runtime import DOMAIN, registry, require_alive
from .transfer import export_markdown

_BATCH_ACTIONS = ("archive", "unarchive", "delete", "export", "pin", "unpin")
_BATCH_MAX = 100


def _unique_ids(ids: object) -> list[str]:
    if isinstance(ids, str) or not isinstance(ids, (list, tuple)):
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT, "ids must be a list of strings")
    seen: set[str] = set()
    out: list[str] = []
    for raw in ids:
        nid = str(raw or "").strip()
        if not nid or nid in seen:
            continue
        seen.add(nid)
        out.append(nid)
    return out


@capability(
    registry,
    name="batch_notes",
    description="Apply the same action to multiple notes: archive|unarchive|delete|export|pin|unpin."
    " Up to 100 ids; per-note failures are recorded in `failed` without aborting the rest."
    " Users and agents invoke this capability equivalently.",
    cost=2,
    reversible=True,
)
async def batch_notes(ids: list[str], action: str) -> dict:
    action = (action or "").strip()
    if action not in _BATCH_ACTIONS:
        raise ServiceError(
            DOMAIN, ErrorSuffix.INVALID_INPUT, f"action must be one of {list(_BATCH_ACTIONS)}"
        )
    nids = _unique_ids(ids)
    if not nids:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT, "ids cannot be empty")
    if len(nids) > _BATCH_MAX:
        raise ServiceError(
            DOMAIN, ErrorSuffix.INVALID_INPUT, f"At most {_BATCH_MAX} notes per call"
        )
    ok: list[str] = []
    failed: list[dict] = []
    paths: list[str] = []
    for nid in nids:
        try:
            if action == "archive":
                await update_note(nid, archived=True)
            elif action == "unarchive":
                await update_note(nid, archived=False)
            elif action == "pin":
                await update_note(nid, pinned=True)
            elif action == "unpin":
                await update_note(nid, pinned=False)
            elif action == "delete":
                await delete_note(nid)
            else:
                exported = export_markdown(require_alive(nid))
                paths.append(exported["path"])
            ok.append(nid)
        except ServiceError as exc:
            failed.append({"id": nid, "error": exc.body.message})
    result: dict = {"ok": ok, "failed": failed, "action": action, "count": len(ok)}
    if paths:
        result["paths"] = paths
    return result
