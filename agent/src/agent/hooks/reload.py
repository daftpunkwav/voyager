"""User hook hot-reload without restarting the agent.

After the user adds/removes/edits declarative hook JSON under `workspace/hooks/`, reload()
applies the changes: remove registrations with the `user:` prefix, reload the directory,
selectively retract domain-event subscriptions declared only by the user side, then converge
subscriptions via the existing EventLoop.sync_extra_patterns callback (the same entry point
PluginManager uses; never a second subscription path).

Design constraints:
- Manual triggering only (reload_user_hooks capability plus a settings-page button); no
  filesystem watching.
- Subscription retraction mirrors plugin semantics: a pattern is forgotten only when the
  reloaded user files no longer declare it, no other loaded source claims it in the registry,
  and no approved plugin still needs it (PluginManager.pattern_still_wanted).
- The directory is fixed to workspace/hooks at assembly time; reload() takes no path argument
  (so arbitrary JSON elsewhere cannot be loaded as hooks). Declarative only -- no scripts.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent.hooks.loader import HookLoader, invalid_on_reason, read_hook_json
from agent.hooks.triggers import HOOK_POINTS, HookRegistry

log = logging.getLogger("agent.hooks.reload")

#: source prefix for user hooks (matches build_agent startup loading; hot-unload removes only
#: this layer)
USER_SOURCE_PREFIX = "user:"


class UserHookReloader:
    """Reload and read-only listing of workspace/hooks user hooks; the capability layer
    delegates here."""

    def __init__(
        self,
        registry: HookRegistry,
        hooks_dir: str | Path,
        *,
        plugins: Any | None = None,  # PluginManager (checks whether a plugin still needs a
        # pattern before unsubscribing)
    ) -> None:
        self._registry = registry
        self._hooks_dir = Path(hooks_dir)
        self._plugins = plugins
        self._sync: Callable[[tuple[str, ...]], None] | None = None

    def set_subscription_sync(self, sync: Callable[[tuple[str, ...]], None] | None) -> None:
        """Inject the subscription-sync callback (called by build_agent once the EventLoop exists).

        Same entry point and semantics as PluginManager.set_subscription_sync: injecting
        performs an immediate sync so patterns loaded at startup are not missed.
        """
        self._sync = sync
        if sync is not None:
            self._sync_subscription()

    def _sync_subscription(self) -> None:
        """Push the current hooks.event_patterns to the EventLoop (no-op without a callback)."""
        if self._sync is not None:
            self._sync(self._registry.event_patterns)

    def reload(self) -> dict:
        """Reload user hooks: unload (user: prefix) -> reinstall -> selective unsubscription
        -> sync.

        Returns `loaded` (files loaded this run), `event_patterns` (the full subscription
        set after reload), and `skipped` (files that could not be loaded, with reasons).
        """
        # 1. Patterns the user side helped declare before the reload (via owner records;
        #    lifecycle points are not recorded, so they are naturally absent -- they never
        #    go through subscriptions)
        old_ons = {
            p
            for p in self._registry.event_patterns
            if any(
                s.startswith(USER_SOURCE_PREFIX) for s in self._registry.pattern_owner_sources(p)
            )
        }
        # 2. Unload only the user: prefix; plugin: and other prefixes stay untouched
        self._registry.remove_source(USER_SOURCE_PREFIX)
        # 3. Reinstall every JSON in the directory; a single bad file is skipped and
        #    reported, never crashing the reload (same tolerance as plugin loading)
        loader = HookLoader(self._registry)
        loaded = 0
        skipped: list[dict] = []
        new_ons: set[str] = set()  # on values of loaded files (input-validated strings)
        # A missing directory yields an empty glob: success with loaded=0 and user hooks
        # cleared; the directory is not created
        for path in sorted(self._hooks_dir.glob("*.json")):
            # Read and validate once here before handing off to the loader (the loader reads
            # the file again from disk); bad files never enter the registry and report a
            # readable reason. The on lookup mirrors the loader exactly (data.get("on", ""))
            # so new_ons stays consistent with the patterns actually recorded in the registry
            data = read_hook_json(path)
            if data is None:
                skipped.append(
                    {"path": path.name, "reason": "unparseable (JSON must be an object)"}
                )
                log.warning("user hook file unparseable, skipped: %s", path)
                continue
            # Same invalid-on decision as the loader: the file is not loaded and the reason
            # is reported in skipped -- no crash, no registration, no subscription
            reason = invalid_on_reason(data.get("on", ""))
            if reason is not None:
                skipped.append({"path": path.name, "reason": reason})
                log.warning("user hook file has an invalid on, skipped: %s (%s)", path, reason)
                continue
            try:
                count = loader.load_file(path, source="user", approved=True)
            except Exception as exc:  # noqa: BLE001  # single-file failure skipped, not fatal
                skipped.append({"path": path.name, "reason": f"failed to load: {exc}"})
                log.warning("user hook file failed to load, skipped: %s", path)
                continue
            if count:
                loaded += count
                on = data.get("on", "")
                if on not in HOOK_POINTS:
                    new_ons.add(on)
        # 4. Selective unsubscription: forget an old user pattern only when the new files no
        #    longer declare it, no other loaded source claims it, and no approved plugin
        #    still needs it -- all three conditions at once.
        #    (key=str defense: sorting must not crash if owner records ever contain a
        #    legacy non-string pattern)
        for pattern in sorted(old_ons - new_ons, key=str):
            if any(
                not s.startswith(USER_SOURCE_PREFIX)
                for s in self._registry.pattern_owner_sources(pattern)
            ):
                continue
            if self._plugins is not None and self._plugins.pattern_still_wanted(pattern):
                continue
            self._registry.forget_event_pattern(pattern)
        # 5. Converge subscriptions (same sync entry point; when not injected, only the
        # registry changes -- the loop-side startup load already subscribed)
        self._sync_subscription()
        return {
            "loaded": loaded,
            "event_patterns": list(self._registry.event_patterns),
            "skipped": skipped,
        }

    def list(self) -> list[dict]:
        """Data source for list_user_hooks: declarations and load state of *.json in the
        directory (read-only).

        `loaded` is based on registry sources (`user:<file stem>`); for a bad file, on is
        empty and enabled is False, so loaded is always False.
        """
        loaded_sources = set(self._registry.sources)
        items: list[dict] = []
        for path in sorted(self._hooks_dir.glob("*.json")):
            data = read_hook_json(path)
            items.append(
                {
                    "path": path.name,
                    "on": str(data.get("on") or "") if data else "",
                    "enabled": bool(data.get("enabled", False)) if data else False,
                    "description": str(data.get("description") or path.stem) if data else "",
                    "loaded": f"{USER_SOURCE_PREFIX}{path.stem}" in loaded_sources,
                }
            )
        return items
