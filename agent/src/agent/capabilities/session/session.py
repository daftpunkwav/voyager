"""session capability: the human REST surface for chat-session management —
one action parameter covers list/create/fork/rename/delete/get/read/search/
trace/pin/archive/set_active.

Same name and same action dispatch as the agent's session tool — both bind
session_action() in tools/session/actions.py (one implementation, two
drivers). The agent's tool adds interaction-integrity guards (it may not
rename/delete/switch the session the user is looking at); the human path
keeps only the manager-level protections (delete refused while running).
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps
from agent.tools.session.actions import session_action


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="session",
        description=(
            "Chat-session management: action list/create/fork/rename/delete/get/"
            "read/search/trace/pin/archive/set_active over the shared SessionManager"
        ),
    )
    def session(
        action: str,
        session_id: str = "",
        title: str = "",
        source_session_id: str = "",
        persona: str = "orchestrator",
        keep_messages: int = 0,
        before_seq: int = 0,
        limit: int = 0,
        query: str = "",
        pinned: bool = True,
        archived: bool = True,
    ) -> dict | list | str:
        return session_action(
            deps.sessions,
            deps.session_index,
            deps.log,
            action=action,
            session_id=session_id,
            title=title,
            source_session_id=source_session_id,
            persona=persona,
            keep_messages=keep_messages,
            before_seq=before_seq,
            limit=limit,
            query=query,
            pinned=pinned,
            archived=archived,
        )
