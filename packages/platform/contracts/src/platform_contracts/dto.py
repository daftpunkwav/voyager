"""Shared DTOs for capability inputs and outputs (pure data)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class JobRef:
    """Long-running job contract: the handler only enqueues and returns this
    reference immediately; progress is reported through the event stream."""

    job_id: str
    status: JobStatus = JobStatus.QUEUED

    def to_dict(self) -> dict[str, Any]:
        return {"job_id": self.job_id, "status": self.status.value}


class HealthStatus(str, Enum):
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class HealthReport:
    """Health snapshot of a single service."""

    service: str
    status: HealthStatus
    detail: str = ""
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "status": self.status.value,
            "detail": self.detail,
            "ts": self.ts,
        }
