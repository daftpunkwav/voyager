"""Declarative hook loading from plugin directories (JSON metadata:
on/description/enabled).

Declarative actions default to logging; executable actions come from the Python register() API.
Plugin hooks require user approval before enabling. `on` is either a lifecycle point in
HOOK_POINTS or a domain event pattern (fnmatch wildcards supported), wrapped as an on_event
filter. Invalid `on` values ("*", empty, non-string) reject the file with a warning, and
unreadable files are skipped instead of crashing startup; all load paths share read_hook_json.
"""

from __future__ import annotations

import fnmatch
import json
import logging
from pathlib import Path

from agent.hooks.triggers import HOOK_POINTS, HookRegistry

log = logging.getLogger("agent.hooks.loader")


def invalid_on_reason(on: object) -> str | None:
    """Return a readable reason when on is invalid, else None (input defense).

    Rejects three cases: "*" (would break EventLoop exact subscriptions if passed into
    event_patterns), an empty or missing value (would register a filter that never matches
    and leave a dead subscription), and non-strings (same subscription pollution). Shared by
    load_file rejection and UserHookReloader.reload's skipped reporting so the two cannot drift.
    """
    if not isinstance(on, str):
        return f"on must be a string, got {on!r}"
    if not on:
        return "on is empty or missing"
    if on == "*":
        return '"*" is forbidden as an event pattern'
    return None


def read_hook_json(path: Path) -> dict | None:
    """Read a single hook JSON; missing / non-UTF-8 / invalid JSON or non-dict data return None.

    Shared by all three load paths (startup, plugin manager, hot reload): a single bad file
    is skipped with a warning instead of crashing build_agent startup.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


class HookLoader:
    def __init__(self, registry: HookRegistry) -> None:
        self._registry = registry

    def load_dir(self, hooks_dir: str | Path, *, source: str, approved: bool) -> int:
        """Load every *.json hook in the directory; skipped entirely when approved=False
        (awaiting user approval)."""
        if not approved:
            return 0
        count = 0
        for path in sorted(Path(hooks_dir).glob("*.json")):
            count += self.load_file(path, source=source, approved=True)
        return count

    def load_file(self, hook_path: str | Path, *, source: str, approved: bool) -> int:
        """Load a single hook JSON: skip disabled and unparseable files (bad files never crash
        startup); reject invalid `on` ("*" / empty / non-string) with a warning."""
        if not approved:
            return 0
        path = Path(hook_path)
        data = read_hook_json(path)
        if data is None:
            log.warning("hook %s unparseable (JSON must be an object), skipped", path)
            return 0
        if not data.get("enabled", False):
            return 0
        on = data.get("on", "")
        reason = invalid_on_reason(on)
        if reason is not None:
            log.warning("hook %s skipped: %s", path, reason)
            return 0
        desc = data.get("description", path.stem)
        src = f"{source}:{path.stem}"

        if on in HOOK_POINTS:

            async def _log_only(_desc: str = desc, **kwargs) -> None:
                log.info("declarative hook fired: %s (%s)", _desc, kwargs)

            self._registry.register(on, _log_only, source=src)
        else:

            async def _on_event_hook(
                event, _pattern: str = on, _desc: str = desc, **_kwargs
            ) -> None:
                """Domain-event filter: log only when the event type matches the pattern
                (wildcards supported)."""
                etype = str(getattr(event, "type", ""))
                if fnmatch.fnmatchcase(etype, _pattern):
                    log.info("declarative hook fired: %s (%s)", _desc, etype)

            self._registry.register("on_event", _on_event_hook, source=src)
            # Record the declared event pattern so EventLoop can subscribe exactly;
            # lifecycle points (on in HOOK_POINTS) are not event types and are not recorded.
            # source is kept to attribute ownership when hot-unloading user/plugin hooks.
            self._registry.record_event_pattern(on, source=src)
        return 1
