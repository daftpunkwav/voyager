"""Invocation-scoped context for capability handlers.

current_chat_session carries the chat session id of the agent turn executing
the capability call (set by the agent runtime at turn entry; asyncio task
context propagates it into async handlers and into to_thread workers). Domain
packages read it to stamp their bus events, so session-filtered consumers
(chat history pages, per-session SSE routing) can attribute those events to
the conversation that caused them. '' = not attributable: the call came from
REST, a background job, or the notes UI rather than a chat turn.
"""

from __future__ import annotations

from contextvars import ContextVar

current_chat_session: ContextVar[str] = ContextVar("capability.current_chat_session", default="")
