"""Side-effect policies for plugin load/revoke, split out of manager.py.

Two kinds of runtime-touching decisions, kept separate from approval-list
orchestration (manager.py):
- External MCP: register pending entries per selection; reclaim via the
  safety chain on revoke/uncheck (skip and disclose when the config
  mismatches, another plugin still needs it, or tools were approved).
- Event subscriptions: on hot-unload/revoke, decide whether a pattern is
  still needed by other approved plugins or loaded user hooks, so shared
  subscriptions are not withdrawn by mistake.

Stateless: manager-side data (manifest list, effective approvals, raw
approvals storage) is always passed in as parameters; no back-dependency
on manager.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from platform_contracts import ActorRef, ServiceError

from agent.hooks.reload import USER_SOURCE_PREFIX
from agent.mcp.pool import validate_server_config
from agent.plugins.manifest import (
    Approval,
    PluginManifest,
    hook_on,
    manifest_hook_entries,
    manifest_mcp_servers,
)

log = logging.getLogger("agent.plugins")


def mcp_tools_approved(mcp: Any, sid: str) -> list[str]:
    """Read-only access to the approved-tools list in the existing MCP store
    (empty when the server is not registered)."""
    if mcp is None:
        return []
    cfg = mcp.find_config(sid)
    if cfg is None:
        return []
    approved = cfg.get("approved") or []
    return list(approved) if isinstance(approved, list) else []


def plugin_server_config(sid: str, raw: object) -> dict:
    """One mcp.json server declaration -> normalized config (shared by
    registration and the reclaim guard so both see the same transform).

    Invalid declarations (missing command, bad url, ...) raise
    AGENT.INVALID_INPUT; callers treat that as a skip.
    """
    entry = dict(raw) if isinstance(raw, dict) else {}
    entry["id"] = str(sid)
    entry.setdefault("kind", "url" if entry.get("url") else "stdio")
    return validate_server_config({**entry, "approval": "item"})


def declared_ons(manifest: PluginManifest) -> set[str]:
    """Set of ``on`` values declared by the plugin's hook files (bad files are
    skipped; both lifecycle points and event types count)."""
    ons: set[str] = set()
    for hook_path, _rel in manifest_hook_entries(manifest):
        on = hook_on(hook_path)
        if on:
            ons.add(on)
    return ons


def pattern_still_wanted(
    name: str,
    pattern: str,
    *,
    manifests: list[PluginManifest],
    approval_of: Callable[[PluginManifest], Approval | None],
) -> bool:
    """Whether other approved plugins would actually load a hook declaring
    this pattern (if so, keep the subscription).

    "Still needed" means the plugin is bundle-approved (hooks_all) or has the
    declaring hook file per-item selected; merely declaring it in the manifest
    is not enough - an unselected file was never registered, and keeping the
    subscription because of it would leave the revoked plugin's pattern
    dangling in event_patterns. Pass an empty name to exclude no plugin
    (the public fallback check used before user-hook hot-reload withdraws a
    subscription).
    """
    for other in manifests:
        if other.name == name:
            continue
        approval = approval_of(other)
        if approval is None:
            continue
        for hook_path, rel in manifest_hook_entries(other):
            if hook_on(hook_path) == pattern and (approval.hooks_all or rel in approval.hooks):
                return True
    return False


def user_hook_declares(pattern: str, *, hooks: Any) -> bool:
    """Whether loaded user hooks still declare this pattern.

    Ownership sources are recorded in HookRegistry at record_event_pattern
    time, so the information is already there: any ``user:``-prefixed source
    means the user side still needs it. Deliberately not injecting a
    UserHookReloader reference into PluginManager: that would widen the
    constructor and add a manager->reload instance dependency, while the
    registry already holds everything the check needs; the ``user:`` prefix
    constant is shared with startup loading (main.py load_dir source="user").
    """
    return any(s.startswith(USER_SOURCE_PREFIX) for s in hooks.pattern_owner_sources(pattern))


def mcp_still_wanted(
    name: str,
    sid: str,
    *,
    manifests: list[PluginManifest],
    approval_of: Callable[[PluginManifest], Approval | None],
) -> bool:
    """Whether other approved plugins still need this mcp server id (same
    spirit as pattern_still_wanted).

    "Still needed" = another plugin is approved, its mcp.json declares the id,
    and (bundle mcp_all or per-item selected); declared but unselected does
    not count, matching per-item load semantics.
    """
    for other in manifests:
        if other.name == name:
            continue
        approval = approval_of(other)
        if approval is None:
            continue
        if sid in manifest_mcp_servers(other) and (approval.mcp_all or sid in approval.mcp):
            return True
    return False


def mcp_selected_ids(
    name: str,
    manifest: PluginManifest | None,
    approval: Approval | None,
    *,
    approvals: dict[str, dict],
) -> set[str]:
    """MCP server ids this plugin actually registered under its current
    approvals.

    With a manifest: declared set intersected with the approval selection
    (bundle mcp_all = all declared; per-item takes the selection restricted to
    declared ids). With the directory deleted: fall back to the id list in
    approvals[name].mcp - "*" or the legacy bundle key stores no ids, so
    ownership cannot be determined and the empty set means nothing is
    reclaimed.
    """
    if manifest is not None:
        if approval is None:
            return set()
        declared = set(manifest_mcp_servers(manifest))
        return declared if approval.mcp_all else (set(approval.mcp) & declared)
    raw = approvals.get(name)
    mcp_raw = raw.get("mcp") if isinstance(raw, dict) else None
    if not isinstance(mcp_raw, list):
        return set()
    return {str(x) for x in mcp_raw if str(x).strip()}


async def reclaim_mcp_servers(
    name: str,
    manifest: PluginManifest | None,
    selected: set[str],
    actor: ActorRef,
    *,
    mcp: Any,
    manifests: list[PluginManifest],
    approval_of: Callable[[PluginManifest], Approval | None],
) -> tuple[list[str], list[dict]]:
    """Reclaim candidate MCP servers via the safety chain; returns
    (reclaimed ids, skipped disclosures).

    Candidates = selected intersected with the current agent.mcp.servers;
    each candidate must pass the whole chain, otherwise it is skipped with a
    disclosed reason - never silently deleted:
    - Config-match guard (manifest present): the current config must equal the
      plugin's mcp.json declaration after the same normalization - a same-id
      config the user hand-added with different parameters is not reclaimed;
    - kept when another approved plugin still needs it;
    - kept when its tools were approved (explicit user reliance; removable
      manually in the external-MCP UI).
    Reclamation mirrors remove_mcp_server: unmount + drop_session +
    delete_config; a per-server failure is recorded in skipped, never rolls
    back the revoke, and does not affect other candidates.
    """
    if mcp is None or not selected:
        return [], []
    declared = manifest_mcp_servers(manifest) if manifest is not None else {}
    reclaimed: list[str] = []
    skipped: list[dict] = []
    for sid in sorted(selected):
        try:
            cfg = mcp.find_config(sid)
            if cfg is None:
                skipped.append({"id": sid, "reason": "config no longer exists"})
                continue
            if manifest is not None:
                try:
                    expected = plugin_server_config(sid, declared.get(sid))
                except ServiceError:
                    # Invalid declaration (was skipped at registration, so this
                    # config must be a hand-added same id): skip honestly instead
                    # of falling into the generic reclaim-failure path, which
                    # would misreport an intentional keep as an error
                    skipped.append(
                        {
                            "id": sid,
                            "reason": "invalid plugin declaration (skipped at registration); not reclaimed",
                        }
                    )
                    continue
                if {k: cfg.get(k) for k in expected} != expected:
                    skipped.append(
                        {
                            "id": sid,
                            "reason": "config does not match the plugin declaration (likely hand-added); not reclaimed",
                        }
                    )
                    continue
            if mcp_still_wanted(name, sid, manifests=manifests, approval_of=approval_of):
                skipped.append({"id": sid, "reason": "still in use by other approved plugins"})
                continue
            if list(cfg.get("approved") or []):
                skipped.append(
                    {
                        "id": sid,
                        "reason": "MCP tools approved, kept; remove it manually in the external MCP settings",
                    }
                )
                continue
            mcp.unmount(sid)
            await mcp.drop_session(sid)
            await mcp.delete_config(sid, actor)
            reclaimed.append(sid)
        except Exception as exc:  # noqa: BLE001  # one server failing must not roll back the revoke
            skipped.append({"id": sid, "reason": f"reclaim failed: {exc}"})
    return reclaimed, skipped


async def register_mcp(
    manifest: PluginManifest, approval: Approval, *, mcp: Any, actor: ActorRef
) -> tuple[int, bool]:
    """Register mcp.json servers as pending MCP entries per the selection
    (reusing add_mcp_server semantics).

    Only bundle-approved (mcp_all) or per-item-selected server ids register;
    missing / empty / bad files -> (0, True); a per-entry validation failure
    skips that entry without failing the approval; an existing same-id config
    (hand-added by the user) is not overwritten. Tools are never
    auto-approved.
    """
    servers = manifest_mcp_servers(manifest)
    if not servers:
        return 0, True
    registered = 0
    for sid, raw in servers.items():
        if not approval.mcp_all and sid not in approval.mcp:
            continue
        try:
            cfg = plugin_server_config(sid, raw)
        except ServiceError as exc:
            log.warning("plugin %s MCP entry %r skipped: %s", manifest.name, sid, exc)
            continue
        if mcp is not None and mcp.find_config(cfg["id"]) is None:
            await mcp.upsert_config({**cfg, "approved": []}, actor)
            registered += 1
    return registered, False


__all__ = [
    "declared_ons",
    "mcp_selected_ids",
    "mcp_still_wanted",
    "mcp_tools_approved",
    "pattern_still_wanted",
    "plugin_server_config",
    "reclaim_mcp_servers",
    "register_mcp",
    "user_hook_declares",
]
