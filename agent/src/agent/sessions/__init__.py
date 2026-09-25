"""Session identity, lifecycle, and chat persistence.

One conversational instance per chat session: the manager owns session
identity and lifecycle (create / fork / rename / delete / active pointer),
the store is the keyed SQLite persistence both the human path and the agent
path drive. Sits between the engine (which executes the instances) and the
orchestrator (which drives the message flow), so neither surface has to
reach across the orchestrator to reach it.
"""

from agent.sessions.manager import CHAT_GOAL, UNTITLED_LABEL, SessionManager, new_session_id
from agent.sessions.store import SessionSnapshot, SessionStore, is_valid_session_id

__all__ = [
    "CHAT_GOAL",
    "UNTITLED_LABEL",
    "SessionManager",
    "SessionSnapshot",
    "SessionStore",
    "is_valid_session_id",
    "new_session_id",
]
