"""Shared event-payload helpers for the source submodules."""

from __future__ import annotations

from typing import Any

from platform_capability import current_chat_session


def with_session(payload: dict[str, Any]) -> dict[str, Any]:
    """Stamp the payload with the chat turn executing the capability call, so
    session-scoped consumers (the activity page's agent attribution) can tell
    agent-driven operations from manual ones; '' outside a turn (REST, UI,
    imports) leaves the payload untouched."""
    session = current_chat_session.get()
    if session:
        return {**payload, "session": session}
    return payload
