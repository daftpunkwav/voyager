"""Plugin discovery, approval, and lifecycle management (bundle or
per-item).

Declarative only: a plugin is a plugin-root subdirectory with a
``plugin.json`` manifest (skills / hooks / mcp); plugins never import
platform code or execute arbitrary code. Pipeline: discover -> user
approval (persisted under ``agent.plugins.approved`` /
``agent.plugins.approvals``, user_only, mutually exclusive on write) ->
load skills into SkillLoader, hooks into HookRegistry, and register MCP
entries as pending (tools are never auto-approved). Loading is idempotent
(hot-unload before apply) and declared event subscriptions are pushed to
the EventLoop after every change, so approval/revocation takes effect
without a restart. MCP reclamation on revoke only touches entries with no
approved tools; skipped cases are disclosed in responses. Install copies a
zip or local directory into ``plugins/<name>/`` behind a strict validation
chain (manifest, path jail, zip slip, symlinks, size limits, conflicts) and
never pre-approves anything; uninstall only removes unapproved plugins.
``_``-prefixed directories are listed like any other plugin; the prefix is
a naming convention, not a loader skip rule. Manifest shapes live in
manifest.py, MCP and subscription-retention policy in effects.py; this
module keeps approval persistence and load/unload orchestration, while
install/uninstall plumbing (source roots, jail validation, placement)
lives in installer.py on top of the file primitives in install.py.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from platform_contracts import ActorRef, ErrorSuffix, ServiceError

# Direct submodule import: bypass package-namespace attributes so the
# __init__ <-> manager import cycle never depends on partially-initialized
# module fallback; the form PLR0402 suggests is exactly that fallback, hence noqa
import agent.plugins.effects as effects  # noqa: PLR0402
from agent.hooks.loader import HookLoader
from agent.hooks.triggers import HookRegistry
from agent.plugins.installer import PluginInstaller
from agent.plugins.manifest import (
    BUNDLE,
    Approval,
    PluginManifest,
    discover,
    hook_enabled,
    hook_on,
    manifest_hook_entries,
    manifest_mcp_servers,
    manifest_skill_entries,
    manifest_skills,
    normalize_items,
    parse_approval,
    parse_choice,
)
from agent.skills.loader import SkillLoader

log = logging.getLogger("agent.plugins")

#: Settings key for the bundle approval list (user_only)
APPROVED_KEY = "agent.plugins.approved"
#: Settings key for per-item approval state (user_only)
APPROVALS_KEY = "agent.plugins.approvals"


class PluginManager:
    """Discovery + approval persistence + load/unload; backs the list and
    approve capabilities at the capability layer. Install/uninstall entry
    points delegate to PluginInstaller."""

    def __init__(
        self,
        root: str | Path,
        *,
        settings: Any,  # SettingsStore (reads/writes agent.plugins.approved/approvals)
        skills: SkillLoader,
        hooks: HookRegistry,
        mcp: Any | None = None,  # McpClientPool (registers MCP entries on approval)
        set_subscription_sync: Callable[[tuple[str, ...]], None] | None = None,
        # subscription sync entry point injected by EventLoop (pushed after load/unload)
        workspace: str | Path | None = None,  # allowed install source root
    ) -> None:
        self._root = Path(root)
        self._settings = settings
        self._skills = skills
        self._hooks = hooks
        self._mcp = mcp
        self._set_subscription_sync = set_subscription_sync
        self._workspace = Path(workspace) if workspace is not None else None
        # Install/uninstall plumbing lives in its own class: the source-root
        # and jail checks are security-sensitive and change for different
        # reasons than the load/approval orchestration kept here.
        self._installer = PluginInstaller(
            root=self._root,
            settings=settings,
            workspace=workspace,
            find=self.find,
            approval_of=self._approval_of,
        )

    def set_subscription_sync(self, sync: Callable[[tuple[str, ...]], None] | None) -> None:
        """Inject/replace the subscription-sync callback (called by build_agent
        after constructing the EventLoop).

        sync receives the full current hooks.event_patterns each time; after
        injection an initial sync runs so plugins loaded before injection
        (startup loading) are not missed.
        """
        self._set_subscription_sync = sync
        if sync is not None:
            self._sync_subscription()

    def _sync_subscription(self) -> None:
        """Push current declarative hook event subscriptions to the EventLoop
        (no-op when no callback was injected).

        Loading (apply/_apply_selected) and hot-unloading (unload/
        _unload_manifest) both change event_patterns, so sync once after each;
        the loop side applies an idempotent diff and only touches the delta.
        """
        if self._set_subscription_sync is not None:
            self._set_subscription_sync(self._hooks.event_patterns)

    # ---- Discovery and approval-shape helpers (source data for list_plugins) ----

    def manifests(self) -> list[PluginManifest]:
        return discover(self._root)

    def find(self, name: str) -> PluginManifest | None:
        return next((m for m in self.manifests() if m.name == name), None)

    def approved_names(self) -> list[str]:
        """Bundle approval list (legacy key)."""
        value = self._settings.get(APPROVED_KEY)
        if not isinstance(value, list):
            return []
        return [str(n) for n in value]

    def loadable_names(self) -> list[str]:
        """Union of both keys (bundle + per-item): candidates for startup
        loading in build_agent."""
        names = list(self.approved_names())
        approvals = self.approvals()
        for n in approvals:
            if n not in names:
                names.append(n)
        return names

    def approvals(self) -> dict[str, dict]:
        """Raw per-item approval storage (new key); malformed shapes are treated
        as empty so a bad value cannot break boot."""
        value = self._settings.get(APPROVALS_KEY)
        if not isinstance(value, dict):
            return {}
        return {str(k): v for k, v in value.items() if isinstance(v, dict)}

    def _approval_of(self, manifest: PluginManifest) -> Approval | None:
        """Currently effective approval for this plugin; None when unapproved.

        Per-item state takes precedence (loaded as-is when present); otherwise
        fall back to the bundle list (legacy data loads as "*"). Malformed or
        empty per-item data (all-empty lists, which the write side rejects)
        yields None, matching write-side semantics: empty means nothing is
        approved, so nothing loads and nothing breaks.
        """
        raw = self.approvals().get(manifest.name)
        if raw is not None:
            approval = parse_approval(raw)
            if approval is not None and approval.empty:
                return None
            return approval
        if manifest.name in set(self.approved_names()):
            return BUNDLE
        return None

    def list(self) -> list[dict]:
        """list_plugins items: stable contract shape plus details.

        Beyond contains counts, each item flattens skills/hooks/mcp details
        (name / on / file path / enabled / currently selected); MCP tool
        approval status is read from the existing MCP store (registered /
        tools_approved), keeping per-item selection separate from registration.
        """
        approvals = self.approvals()
        items = []
        for m in self.manifests():
            approval = self._approval_of(m)
            skills_seen: dict[str, Path] = {}
            for skill_dir, sname in manifest_skill_entries(m):
                skills_seen.setdefault(sname, skill_dir)
            hook_entries = manifest_hook_entries(m)
            servers = manifest_mcp_servers(m)
            if approval is None:
                granularity = ""
            elif m.name in approvals:
                granularity = "item"
            else:  # can only be on the bundle list
                granularity = "bundle"
            selected_skills = None if approval is None or approval.skills_all else approval.skills
            selected_hooks = None if approval is None or approval.hooks_all else approval.hooks
            selected_mcp = None if approval is None or approval.mcp_all else approval.mcp
            items.append(
                {
                    "name": m.name,
                    "version": m.version,
                    "description": m.description,
                    "approved": approval is not None,
                    "granularity": granularity,
                    "permissions": {
                        "scopes": [str(s) for s in normalize_items(m.permissions.get("scopes"))],
                        "network": str(m.permissions.get("network") or ""),
                        "fs": str(m.permissions.get("fs") or ""),
                    },
                    "contains": {
                        "skills": len(manifest_skills(m)),
                        "hooks": len(hook_entries),
                        "mcp": bool(servers),
                    },
                    "skills": [
                        {
                            "name": name,
                            "approved": approval is not None
                            and (selected_skills is None or name in selected_skills),
                        }
                        for name in skills_seen
                    ],
                    "hooks": [
                        {
                            "path": rel,
                            "on": hook_on(path),
                            "enabled": hook_enabled(path),
                            "approved": approval is not None
                            and (selected_hooks is None or rel in selected_hooks),
                        }
                        for path, rel in hook_entries
                    ],
                    "mcp": [
                        {
                            "id": sid,
                            "approved": approval is not None
                            and (selected_mcp is None or sid in selected_mcp),
                            "registered": self._mcp is not None
                            and self._mcp.find_config(sid) is not None,
                            "tools_approved": effects.mcp_tools_approved(self._mcp, sid),
                        }
                        for sid in servers
                    ],
                    "path": m.path.name,
                }
            )
        return items

    # ---- Load / hot-unload (shared by build_agent startup and approvals) ----

    def apply(self, name: str) -> dict:
        """Load the plugin per its persisted approval (startup / re-apply).

        Unapproved (or missing plugin directory) -> empty load, no error;
        per-item state still loads only the selected subset.
        """
        manifest = self._require(name)
        approval = self._approval_of(manifest)
        if approval is None:
            return {"skills": [], "hooks": 0}
        return self._apply_selected(manifest, approval)

    def _apply_selected(self, manifest: PluginManifest, approval: Approval) -> dict:
        """Load the plugin's skill dirs and hook files filtered by selection;
        returns loaded counts.

        Hot-unload before load (idempotent): repeated approvals, approval
        retries, and selection changes never double-register hooks or add
        duplicate skill roots.
        """
        self._unload_manifest(manifest)
        skill_names: list[str] = []
        for skill_dir, sname in manifest_skill_entries(manifest):
            if approval.skills_all or sname in approval.skills:
                self._skills.add_root(skill_dir)
                skill_names.append(sname)
        hook_count = 0
        loader = HookLoader(self._hooks)
        for hook_path, rel in manifest_hook_entries(manifest):
            if not (approval.hooks_all or rel in approval.hooks):
                continue
            try:
                hook_count += loader.load_file(
                    hook_path, source=f"plugin:{manifest.name}", approved=True
                )
            except Exception:  # noqa: BLE001  # a bad json file must not fail approval
                log.warning("plugin %s hook file failed to load: %s", manifest.name, rel)
        self._sync_subscription()  # loading changed event subscriptions; sync to loop
        return {"skills": skill_names, "hooks": hook_count}

    def unload(self, name: str) -> dict:
        """Hot-unload: remove skill roots and hook registrations from this
        plugin's source; returns removal counts."""
        return self._unload_manifest(self._require(name))

    def _unload_manifest(self, manifest: PluginManifest) -> dict:
        """Hot-unload per manifest; shared by approve (for idempotency) and unload."""
        removed_skills = 0
        for skill_dir in manifest_skills(manifest):
            if self._skills.remove_root(skill_dir):
                removed_skills += 1
        removed_hooks = self._hooks.remove_source(f"plugin:{manifest.name}:")
        # Withdraw event subscriptions declared by this plugin (exact matching),
        # but keep a pattern when other approved plugins still declare it (do
        # not break their hook triggers) or when loaded user hooks still declare
        # it: the retention decision is symmetric in both directions.
        # remove_source already drops this plugin's ownership records, so kept
        # subscriptions carry no ghost ownership.
        for on in effects.declared_ons(manifest):
            if effects.pattern_still_wanted(
                manifest.name,
                on,
                manifests=self.manifests(),
                approval_of=self._approval_of,
            ):
                continue
            if effects.user_hook_declares(on, hooks=self._hooks):
                continue
            self._hooks.forget_event_pattern(on)
        self._sync_subscription()  # unloading changed event subscriptions; sync to loop
        return {"skills": removed_skills, "hooks": removed_hooks}

    # ---- Approve / revoke (capability-layer entry points; actor goes to audit) ----

    async def approve(self, name: str, actor: ActorRef) -> dict:
        """Bundle approval: load all three groups; register MCP entries as
        pending; never auto-approve tools."""
        manifest = self._require(name)
        loaded = self._apply_selected(manifest, BUNDLE)
        registered, mcp_skipped = await effects.register_mcp(
            manifest, BUNDLE, mcp=self._mcp, actor=actor
        )
        names = self.approved_names()
        if manifest.name not in names:
            await self._settings.set(APPROVED_KEY, sorted([*names, manifest.name]), actor)
        # Previously approved per-item: bundle approval overrides and clears the
        # per-item state to keep the read side unambiguous
        if manifest.name in self.approvals():
            await self._clear_approvals(manifest.name, actor)
        return self._approval_result(manifest.name, loaded, registered, mcp_skipped)

    async def approve_item(
        self,
        name: str,
        actor: ActorRef,
        *,
        skills: object = None,
        hooks: object = None,
        mcp: object = None,
    ) -> dict:
        """Per-item approval: load only the selected skills / hooks / MCP;
        reject empty submissions; disclose unknown names as skipped.

        Unchecking a previously approved MCP id reclaims it under the same
        safety rules as a full revoke; results are disclosed in the response
        as mcp_reclaimed / mcp_reclaim_skipped.
        """
        manifest = self._require(name)
        old = self._approval_of(manifest)  # pre-change approval, needed for reclaim diff
        skills_all, skills_set = parse_choice(skills, "skills")
        hooks_all, hooks_set = parse_choice(hooks, "hooks")
        mcp_all, mcp_set = parse_choice(mcp, "mcp")
        approval = Approval(
            skills_all=skills_all,
            skills=frozenset(skills_set),
            hooks_all=hooks_all,
            hooks=frozenset(hooks_set),
            mcp_all=mcp_all,
            mcp=frozenset(mcp_set),
        )
        if approval.empty:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                "custom approval requires at least one selected item (skill / hook / MCP)",
            )
        loaded = self._apply_selected(manifest, approval)
        skipped = self._skipped_for(manifest, approval)
        registered, mcp_reg_skipped = await effects.register_mcp(
            manifest, approval, mcp=self._mcp, actor=actor
        )
        payload = {
            "skills": "*" if skills_all else sorted(skills_set),
            "hooks": "*" if hooks_all else sorted(hooks_set),
            "mcp": "*" if mcp_all else sorted(mcp_set),
        }
        await self._settings.set(APPROVALS_KEY, {**self.approvals(), manifest.name: payload}, actor)
        # Previously bundle-approved: per-item approval overrides; remove from
        # the bundle list (writes to the two keys are mutually exclusive)
        if manifest.name in self.approved_names():
            names = [n for n in self.approved_names() if n != manifest.name]
            await self._settings.set(APPROVED_KEY, names, actor)
        # Reclaim MCP ids that were selected before but not now, via the same
        # safe chain as a full revoke
        reclaimed, reclaim_skipped = await effects.reclaim_mcp_servers(
            name,
            manifest,
            effects.mcp_selected_ids(name, manifest, old, approvals=self.approvals())
            - effects.mcp_selected_ids(name, manifest, approval, approvals=self.approvals()),
            actor,
            mcp=self._mcp,
            manifests=self.manifests(),
            approval_of=self._approval_of,
        )
        return {
            **self._approval_result(manifest.name, loaded, registered, mcp_reg_skipped),
            "skipped": skipped,
            "granularity": "item",
            "mcp_reclaimed": reclaimed,
            "mcp_reclaim_skipped": reclaim_skipped,
        }

    async def unapprove(self, name: str, actor: ActorRef) -> dict:
        """Revoke (both bundle and per-item): clear both keys, hot-unload, and
        reclaim registered MCP entries per the safety rules.

        The plugin directory may already be gone while the approval list still
        has the entry: revocation must still clear the list, otherwise the dead
        entry can never be removed. Hot-unload runs normally when the manifest
        exists and is skipped otherwise (unloaded counts 0). MCP reclamation
        only touches entries this plugin registered that have no approved
        tools; the rest are skipped and disclosed.
        """
        manifest = self.find(name)
        approval = self._approval_of(manifest) if manifest is not None else None
        unloaded = self._unload_manifest(manifest) if manifest else {"skills": 0, "hooks": 0}
        reclaimed, reclaim_skipped = await effects.reclaim_mcp_servers(
            name,
            manifest,
            effects.mcp_selected_ids(name, manifest, approval, approvals=self.approvals()),
            actor,
            mcp=self._mcp,
            manifests=self.manifests(),
            approval_of=self._approval_of,
        )
        names = [n for n in self.approved_names() if n != name]
        await self._settings.set(APPROVED_KEY, names, actor)
        if name in self.approvals():
            await self._clear_approvals(name, actor)
        return {
            "name": name,
            "approved": False,
            "loaded": {"skills": [], "hooks": 0, "mcp_registered": 0, "mcp_skipped": False},
            "unloaded": unloaded,
            "skipped": {"skills": [], "hooks": [], "mcp": []},
            "mcp_reclaimed": reclaimed,
            "mcp_reclaim_skipped": reclaim_skipped,
        }

    # ---- Install / uninstall (capability-layer entry points) ----
    # Plumbing (source roots, jail validation, placement) lives in
    # PluginInstaller; these delegates keep the capability surface unchanged.

    def install(self, *, zip_path: str = "", source_dir: str = "", overwrite: bool = False) -> dict:
        """Install a plugin from a zip (server-side absolute path) or a local
        directory into plugins/<name>/ (delegates to the installer)."""
        return self._installer.install(
            zip_path=zip_path, source_dir=source_dir, overwrite=overwrite
        )

    def uninstall(self, name: str) -> dict:
        """Delete the directory of an **unapproved** plugin (delegates to the
        installer)."""
        return self._installer.uninstall(name)

    # ---- Internals ----

    def _approval_result(self, name: str, loaded: dict, registered: int, mcp_skipped: bool) -> dict:
        """Approval success payload: loaded contract plus top-level skipped
        (disclosure of unknown per-item names)."""
        return {
            "name": name,
            "approved": True,
            "loaded": {**loaded, "mcp_registered": registered, "mcp_skipped": mcp_skipped},
            "skipped": {"skills": [], "hooks": [], "mcp": []},
        }

    def _skipped_for(self, manifest: PluginManifest, approval: Approval) -> dict:
        """Selected names absent from the current manifest: skipped, not loaded;
        persisted selections are kept untouched."""
        valid_skills = {sname for _d, sname in manifest_skill_entries(manifest)}
        valid_hooks = {rel for _p, rel in manifest_hook_entries(manifest)}
        valid_mcp = set(manifest_mcp_servers(manifest))
        return {
            "skills": sorted(approval.skills - valid_skills),
            "hooks": sorted(approval.hooks - valid_hooks),
            "mcp": sorted(approval.mcp - valid_mcp),
        }

    async def _clear_approvals(self, name: str, actor: ActorRef) -> None:
        approvals = dict(self.approvals())
        approvals.pop(name, None)
        await self._settings.set(APPROVALS_KEY, approvals, actor)

    def _require(self, name: str) -> PluginManifest:
        manifest = self.find(name)
        if manifest is None:
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND, f"no such plugin: {name}")
        return manifest

    def pattern_still_wanted(self, pattern: str) -> bool:
        """Whether any approved plugin would still load a hook declaring this
        pattern.

        Fallback check before user-hook hot-reload withdraws a subscription:
        same file-level semantics as the unload-time check but without
        excluding any plugin; combined with HookRegistry ownership records,
        the subscription is kept if either check holds.
        """
        return effects.pattern_still_wanted(
            "", pattern, manifests=self.manifests(), approval_of=self._approval_of
        )
