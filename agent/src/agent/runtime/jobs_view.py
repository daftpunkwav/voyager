"""Background-job projection: task.* events folded into a
read-only view the model can query, without importing any domain.

Only the event log is read; a job's identity comes from its payload
(job_id / run_id), its status from the newest event seen. Cancellation is
NOT implemented here: cancel_job routes to the source domain's own cancel
capability through the host-provided router (the agent never learns domain
implementations).
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from platform_contracts import DomainEvent
from platform_eventbus import EventLog

_TASK_TYPES = (
    DomainEvent.TASK_ENQUEUED,
    DomainEvent.TASK_PROGRESS,
    DomainEvent.TASK_COMPLETED,
    DomainEvent.TASK_FAILED,
)
_MAX_JOBS = 200
_MAX_TITLE = 120


class JobsView:
    """task.* event stream -> bounded latest-status map (rebuilt on demand;
    the event log stays the source of truth)."""

    def __init__(self, log: EventLog) -> None:
        self._log = log

    def list_jobs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        jobs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for _seq, event in self._log.read_before(
            before_seq=self._log.latest_seq() + 1, types=_TASK_TYPES, limit=2000
        ):
            payload = event.payload or {}
            jid = str(payload.get("job_id") or payload.get("run_id") or "")
            if not jid:
                continue
            status = {
                DomainEvent.TASK_ENQUEUED: "queued",
                DomainEvent.TASK_PROGRESS: "running",
                DomainEvent.TASK_COMPLETED: "completed",
                DomainEvent.TASK_FAILED: "failed",
            }.get(event.type, "running")
            entry = jobs.get(jid)
            if entry is None:
                if len(jobs) >= _MAX_JOBS:
                    jobs.popitem(last=False)  # evict oldest
                entry = {
                    "job_id": jid,
                    "kind": str(payload.get("kind") or ""),
                    "title": str(payload.get("title") or payload.get("goal") or "")[:_MAX_TITLE],
                    "source": str(payload.get("source") or event.type.split(".")[0]),
                    "status": status,
                    "ts": event.ts,
                }
                jobs[jid] = entry
            else:
                entry["status"] = status
                entry["ts"] = event.ts
                if status == "failed" and payload.get("error"):
                    entry["error"] = str(payload["error"])[:300]
        rows = list(jobs.values())
        return rows[-max(1, limit) :][::-1]  # newest first

    def find(self, job_id: str) -> dict[str, Any] | None:
        for row in self.list_jobs(limit=_MAX_JOBS):
            if row["job_id"] == job_id:
                return row
        return None


__all__ = ["JobsView"]
