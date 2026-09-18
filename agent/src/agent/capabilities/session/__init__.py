"""Session capability group (chat-session management, the human path).
Zero-logic aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.session.archive_session import register as _archive_session
from agent.capabilities.session.delete_session import register as _delete_session
from agent.capabilities.session.get_session import register as _get_session
from agent.capabilities.session.pin_session import register as _pin_session
from agent.capabilities.session.rename_session import register as _rename_session
from agent.capabilities.session.session_create import register as _session_create
from agent.capabilities.session.session_fork import register as _session_fork
from agent.capabilities.session.session_list import register as _session_list
from agent.capabilities.session.set_active_session import register as _set_active_session


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _session_list(reg, deps)
    _session_create(reg, deps)
    _rename_session(reg, deps)
    _delete_session(reg, deps)
    _set_active_session(reg, deps)
    _session_fork(reg, deps)
    _get_session(reg, deps)
    _pin_session(reg, deps)
    _archive_session(reg, deps)
