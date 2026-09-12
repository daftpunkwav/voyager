"""Hook point triggering: registration and firing; hook exceptions never
break the main flow.

Responsibilities:
- HookRegistry: register/fire hooks at fixed lifecycle points (HOOK_POINTS)
- Track declarative on_event patterns and per-source ownership so hot-reload and
  plugin revocation can decide whether a subscription is still needed
- remove_source strips one source prefix's registrations and ownership records
- fire() isolates per-hook failures (log only); pre_tool returning False intercepts
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from platform_capability import AuditEntry
from platform_contracts import ErrorSuffix, ServiceError

HOOK_POINTS = (
    "on_event",  # domain event arrival
    "pre_tool",  # before a tool call (may rewrite/intercept by returning False)
    "post_tool",  # after a tool call
    "on_subagent_start",
    "on_subagent_end",
    "on_user_message",
)

HookFn = Callable[..., Awaitable[Any]]

log = logging.getLogger("agent.hooks")


class HookRegistry:
    def __init__(self, auditor: Any = None) -> None:
        # Optional audit sink (AuditSink protocol): every hook execution is
        # user/plugin code, so its action must land in the same audit chain as
        # capability calls (R6 symmetric audit). None = unaudited (tests)
        self._auditor = auditor
        self._hooks: dict[str, list[tuple[str, HookFn]]] = {p: [] for p in HOOK_POINTS}
        # Domain event patterns declared by declarative hooks (declaration order kept, deduped):
        # used by EventLoop for exact subscription. Pure-Python register("on_event") hooks
        # are not tracked here
        self._event_patterns: list[str] = []
        # pattern -> set of loaded sources that declared it: used by user hook hot-reload to
        # decide whether anything besides the user side still needs a subscription. Grows on
        # record, is removed wholesale on forget, and remove_source strips ownership of the
        # unloaded prefix (preventing ghost ownership)
        self._pattern_owners: dict[str, set[str]] = {}

    def record_event_pattern(self, pattern: str, source: str = "") -> None:
        """Record a domain event type (fnmatch wildcards supported) when the loader wraps
        on_event, for subscription.

        When source is non-empty, ownership is recorded too: the same pattern may be declared
        jointly by user hooks and multiple plugins; when one side is hot-unloaded, this decides
        whether the subscription is still needed by others.
        """
        if pattern not in self._event_patterns:
            self._event_patterns.append(pattern)
        if source:
            self._pattern_owners.setdefault(pattern, set()).add(source)

    def forget_event_pattern(self, pattern: str) -> None:
        """Retract a declared event subscription when a plugin approval is revoked; unknown
        patterns are a no-op."""
        if pattern in self._event_patterns:
            self._event_patterns.remove(pattern)
        self._pattern_owners.pop(pattern, None)

    @property
    def event_patterns(self) -> tuple[str, ...]:
        """Domain event types declared by declarative hooks; lifecycle points are excluded."""
        return tuple(self._event_patterns)

    def pattern_owner_sources(self, pattern: str) -> tuple[str, ...]:
        """Loaded sources that declared the pattern (stable order; empty when undeclared)."""
        return tuple(sorted(self._pattern_owners.get(pattern, ())))

    @property
    def sources(self) -> tuple[str, ...]:
        """All currently registered sources (deduped, order kept; used by list_user_hooks)."""
        seen: dict[str, None] = {}
        for entries in self._hooks.values():
            for source, _fn in entries:
                seen.setdefault(source, None)
        return tuple(seen)

    def register(self, point: str, fn: HookFn, *, source: str = "local") -> None:
        if point not in self._hooks:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"unknown hook point: {point} (valid: {HOOK_POINTS})",
            )
        self._hooks[point].append((source, fn))

    def remove_source(self, prefix: str) -> int:
        """Remove registrations whose source starts with the prefix, along with their event
        pattern ownership (plugin hot-unload).

        Ownership records are removed together with the registrations: once a side is
        unloaded, its "declared this pattern" is no longer true, and a leftover ghost source
        would pin the other side's subscription-retention decision forever (user reload /
        plugin revocation). Whether a pattern leaves event_patterns is still an explicit
        forget by the caller -- after unloading one side, the other may still need the
        subscription. Returns the number of removed hook registrations.
        """
        removed = 0
        for point, entries in self._hooks.items():
            kept = [(s, fn) for s, fn in entries if not s.startswith(prefix)]
            removed += len(entries) - len(kept)
            self._hooks[point] = kept
        for pattern, owners in list(self._pattern_owners.items()):
            kept_owners = {s for s in owners if not s.startswith(prefix)}
            if len(kept_owners) != len(owners):
                if kept_owners:
                    self._pattern_owners[pattern] = kept_owners
                else:
                    del self._pattern_owners[pattern]
        return removed

    async def fire(self, point: str, **kwargs: Any) -> list[Any]:
        """Fire in order; a single hook failure is only logged. Any pre_tool hook returning
        False means interception. Each hook execution writes one audit entry
        (duration + outcome) when an auditor is wired."""
        results = []
        for source, fn in self._hooks.get(point, []):
            started = time.perf_counter()
            ok = True
            try:
                results.append(await fn(**kwargs))
            except Exception:  # isolate hook failures
                ok = False
                log.exception("hook failed (%s @ %s)", source, point)
            finally:
                if self._auditor is not None:
                    self._auditor(
                        AuditEntry(
                            actor_id=f"hook:{source}",
                            actor_kind="system",
                            capability=f"hook.{point}",
                            args_summary="",
                            ok=ok,
                            error_code="" if ok else "HOOK_FAILED",
                            trace_id="",
                            ms=round((time.perf_counter() - started) * 1000, 1),
                        )
                    )
        return results

    def registered(self) -> dict[str, int]:
        return {p: len(fns) for p, fns in self._hooks.items() if fns}
