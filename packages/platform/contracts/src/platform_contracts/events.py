"""Event contracts: the envelope structure and event-type vocabulary.

Every event carries id / type / actor / payload / ts / trace_id. The event
type vocabulary is an open initial set: new types are registered and used by
the services that publish them without changing this package; commonly shared
types are promoted here.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ActorKind(str, Enum):
    """Actor kinds.

    During the local single-user phase, user actors always have id="local";
    the structure is reserved for multi-user. system is an infrastructure
    identity outside the three kinds, used by platform facilities such as
    health probes and process supervision, distinguished from user/agent
    actions in audits and events.
    """

    USER = "user"
    AGENT = "agent"
    EXTERNAL = "external"
    SYSTEM = "system"


@dataclass(frozen=True)
class ActorRef:
    """Actor reference carried by events and call chains (pure data)."""

    kind: ActorKind
    id: str
    scopes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "id": self.id, "scopes": list(self.scopes)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActorRef:
        return cls(
            kind=ActorKind(data["kind"]),
            id=str(data["id"]),
            scopes=tuple(data.get("scopes") or ()),
        )


#: Constant user actor for the local single-user phase
LOCAL_USER = ActorRef(kind=ActorKind.USER, id="local")


def new_trace_id() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True)
class Event:
    """Event envelope. ts is epoch seconds (float); payload must be JSON-serializable."""

    type: str
    actor: ActorRef
    payload: dict[str, Any]
    trace_id: str = field(default_factory=new_trace_id)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "actor": self.actor.to_dict(),
            "payload": self.payload,
            "ts": self.ts,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            actor=ActorRef.from_dict(data["actor"]),
            payload=dict(data.get("payload") or {}),
            ts=float(data["ts"]),
            trace_id=str(data.get("trace_id") or ""),
        )


class DomainEvent:
    """Domain event vocabulary (open initial set).

    Topics consumed across services (the gateway Chat stream, agent
    observation subscriptions, etc.) must use these constants on both the
    publisher and subscriber sides; scattering literals is not allowed.
    Events purely internal to a service may use literals.
    """

    USER_MESSAGE = "user.message"
    USER_ONLINE = "user.online"
    USER_ACTIVITY = "user.activity"
    TASK_ENQUEUED = "task.enqueued"
    TASK_PROGRESS = "task.progress"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    AGENT_MESSAGE = "agent.message"
    AGENT_ASK = "agent.ask"
    AGENT_STEP = "agent.step"
    AGENT_DELTA = "agent.delta"
    AGENT_OBSERVE = "agent.observe"
    AGENT_POLICY_NOTIFY = "agent.policy.notify"
    AGENT_NAVIGATE = "agent.navigate"
    NOTE_CREATED = "note.created"
    NOTE_EDITED = "note.edited"
    NOTE_DELETED = "note.deleted"
    NOTE_RESTORED = "note.restored"
    NOTE_PURGED = "note.purged"
    NOTE_PURGED_BATCH = "note.purged_batch"
    NOTES_UI_CHANGED = "notes.ui.changed"
    SOURCE_ADDED = "source.added"
    SOURCE_READY = "source.ready"
    SOURCE_REMOVED = "source.removed"
    SETTINGS_CHANGED = "settings.changed"
    LLM_FALLBACK = "llm.fallback"
    GRAPH_ENGINE_FALLBACK = "graph.engine.fallback"
    SERVICE_HEALTH_CHANGED = "service.health.changed"


class RuntimeEvent:
    """Runtime-level events (internal to the agent)."""

    RUN_STARTED = "RunStarted"
    LLM_STARTED = "LLMStarted"
    LLM_STREAMING = "LLMStreaming"
    LLM_COMPLETED = "LLMCompleted"
    TOOL_STARTED = "ToolStarted"
    TOOL_COMPLETED = "ToolCompleted"
    TOOL_FAILED = "ToolFailed"
    AGENT_PAUSED = "AgentPaused"
    AGENT_RESUMED = "AgentResumed"
    AGENT_COMPLETED = "AgentCompleted"
    AGENT_CANCELLED = "AgentCancelled"
    RUN_FAILED = "RunFailed"
    RUN_CANCELLED = "RunCancelled"
