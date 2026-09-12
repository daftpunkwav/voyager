"""Plugin install/uninstall plumbing: source resolution, jail validation,
and placement on disk.

Split from PluginManager (which keeps discovery, approval, and load/unload
orchestration) so the security-sensitive install surface - source roots,
path jail, overwrite rules - changes for its own reasons and can be
reviewed and tested in isolation. Declarative only: no plugin script is
ever executed and there is no post-install hook. File-movement primitives
(zip extraction, directory prep, copytree) live in install.py; this module
adds the policy decisions on top of them:

- Source: exactly one of zip_path / source_dir; the path must be absolute
  and resolve inside an allowed root (workspace + agent.fs read/write
  roots, read live at install time).
- Placement: copytree into plugins/<name>/ after manifest, name, jail, and
  conflict validation; any failure leaves no half-installed directory.
- Uninstall: only unapproved plugins; approved plugins must be revoked
  first (approval cleanup and MCP reclamation go through the manager's
  unapprove chain, not duplicated here).
"""

from __future__ import annotations

import builtins
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from platform_contracts import ErrorSuffix, ServiceError

from agent.plugins.install import (
    extract_plugin_zip,
    place_plugin,
    prepare_source_dir,
    safe_plugin_name,
)
from agent.plugins.manifest import (
    PluginManifest,
    load_manifest,
    manifest_hook_entries,
    manifest_mcp_servers,
    manifest_skills,
    normalize_items,
    resolve_within,
)

log = logging.getLogger("agent.plugins")


class PluginInstaller:
    """Install/uninstall a plugin directory behind the validation chain.

    Discovery and approval state are not owned here: the manager injects
    ``find`` (discovery lookup) and ``approval_of`` (approval lookup) so
    conflict/overwrite/uninstall checks read live state without this class
    depending on the manager.
    """

    def __init__(
        self,
        *,
        root: str | Path,
        settings: Any,  # SettingsStore (reads agent.fs read/write roots)
        workspace: str | Path | None,
        find: Any,  # Callable[[str], PluginManifest | None] (manager discovery)
        approval_of: Any,  # Callable[[PluginManifest], Approval | None]
    ) -> None:
        self._root = Path(root)
        self._settings = settings
        self._workspace = Path(workspace) if workspace is not None else None
        self._find = find
        self._approval_of = approval_of

    def install(self, *, zip_path: str = "", source_dir: str = "", overwrite: bool = False) -> dict:
        """Install a plugin from a zip (server-side absolute path) or a local
        directory into plugins/<name>/.

        Copies, never moves; any validation failure, conflict, or size-limit
        hit rejects the whole plugin and leaves no half-installed directory.
        Does not write approvals, register MCP, or load skills/hooks:
        visible in discovery, loaded only after approval.
        """
        has_zip = bool(str(zip_path or "").strip())
        has_dir = bool(str(source_dir or "").strip())
        if has_zip == has_dir:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                "provide exactly one of zip_path and source_dir",
            )
        if has_zip:
            src = self._resolve_source(zip_path, "zip_path")
            with tempfile.TemporaryDirectory(prefix="plugin-install-") as tmp:
                plugin_root = extract_plugin_zip(src, Path(tmp))
                return self._place_validated(plugin_root, overwrite)
        plugin_root = prepare_source_dir(self._resolve_source(source_dir, "source_dir"))
        return self._place_validated(plugin_root, overwrite)

    def uninstall(self, name: str) -> dict:
        """Delete the directory of an **unapproved** plugin; approved plugins
        must be revoked first (approval cleanup and MCP reclamation go through
        unapprove's safe chain, not duplicated here). Missing dir -> NOT_FOUND."""
        manifest = self._require(name)
        if self._approval_of(manifest) is not None:
            raise ServiceError(
                "agent",
                ErrorSuffix.CONFLICT,
                f"plugin {name} is approved; revoke approval before uninstalling",
            )
        target = manifest.path
        if target.is_symlink():  # deleting through a link would destroy the target tree
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"plugin directory is a symlink; refusing to delete (handle it manually): {target}",
            )
        shutil.rmtree(target)
        log.info("plugin %s uninstalled (directory %s deleted)", name, target)
        return {"name": name, "uninstalled": True, "path": target.name}

    def _require(self, name: str) -> PluginManifest:
        manifest = self._find(name)
        if manifest is None:
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND, f"no such plugin: {name}")
        return manifest

    def _resolve_source(self, raw: object, field: str) -> Path:
        """Install source path: must be absolute and live under an allowed root
        (read live at install time)."""
        text = str(raw or "").strip()
        if not text:
            raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, f"{field} must not be empty")
        candidate = Path(text)
        if not candidate.is_absolute():
            raise ServiceError(
                "agent", ErrorSuffix.INVALID_INPUT, f"{field} must be an absolute path: {text!r}"
            )
        resolved = candidate.resolve()
        roots = self._allowed_source_roots()
        if not any(resolved == r or r in resolved.parents for r in roots):
            raise ServiceError(
                "agent",
                ErrorSuffix.FORBIDDEN,
                "install source must be inside the working directory or an additional"
                " read-only/read-write root (configure allowed roots under 'File access'"
                " in the settings page)",
            )
        return resolved

    def _allowed_source_roots(self) -> builtins.list[Path]:
        """Allowed install-source roots: workspace + agent.fs.read_roots +
        agent.fs.write_roots."""
        roots: list[Path] = []
        if self._workspace is not None:
            roots.append(self._workspace)
        for key in ("agent.fs.read_roots", "agent.fs.write_roots"):
            value = self._settings.get(key)
            if isinstance(value, (list, tuple)):
                roots.extend(Path(str(r)) for r in value if str(r).strip())
        return [r.resolve() for r in roots]

    def _place_validated(self, plugin_root: Path, overwrite: bool) -> dict:
        """Place on disk after manifest/name/jail/conflict validation passes."""
        manifest = load_manifest(plugin_root)
        if manifest is None:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                "plugin.json missing or invalid (must be a JSON object containing name)",
            )
        name = safe_plugin_name(manifest.name)
        self._check_contains_jail(manifest)
        dest = self._root / name
        # Source is the destination (using an installed dir as its own source):
        # place_plugin clears dest (= source) before copying, which would be
        # self-destruction; reject explicitly to protect the source directory
        if plugin_root.resolve() == dest.resolve():
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"install source is the same as the target directory plugins/{name} (the plugin is already there);"
                " use a different source, or delete it and reinstall",
            )
        existing = self._find(name)
        # Approved plugins are never overwritten, even with overwrite=true
        if existing is not None and self._approval_of(existing) is not None:
            raise ServiceError(
                "agent",
                ErrorSuffix.CONFLICT,
                f"plugin {name} is approved; revoke approval before overwriting it",
            )
        if not overwrite and (existing is not None or dest.exists()):
            raise ServiceError(
                "agent",
                ErrorSuffix.CONFLICT,
                f"a plugin named {name} already exists; pass overwrite=true explicitly to replace it",
            )
        try:
            place_plugin(plugin_root, dest)
        except Exception:
            shutil.rmtree(dest, ignore_errors=True)  # no half-installed directory on failure
            raise
        # Stale copies with the same name but a different directory name (e.g.
        # a `_`-prefixed alias dir): clean up after a successful placement to
        # avoid two identities for one plugin; if deletion fails (file locked),
        # log only - do not roll back the install
        if existing is not None and existing.path != dest and existing.path.is_dir():
            shutil.rmtree(existing.path, ignore_errors=True)
            if existing.path.exists():
                log.warning(
                    "failed to delete the old directory of plugin %s: %s", name, existing.path
                )
        final = load_manifest(dest) or manifest
        log.info(
            "plugin %s v%s installed at %s (unapproved; loads after user approval)",
            name,
            final.version,
            dest,
        )
        return {
            "name": name,
            "version": final.version,
            "path": dest.name,
            "permissions": {
                "scopes": [str(s) for s in normalize_items(final.permissions.get("scopes"))],
                "network": str(final.permissions.get("network") or ""),
                "fs": str(final.permissions.get("fs") or ""),
            },
            "contains_summary": {
                "skills": len(manifest_skills(final)),
                "hooks": len(manifest_hook_entries(final)),
                "mcp": bool(manifest_mcp_servers(final)),
            },
        }

    def _check_contains_jail(self, manifest: PluginManifest) -> None:
        """Proactively validate at install time that every contains entry stays
        inside the plugin directory; an escape rejects the whole plugin."""
        escaped: list[str] = []
        for field in ("skills", "hooks"):
            for rel in normalize_items(manifest.contains.get(field)):
                if resolve_within(manifest.path, rel) is None:
                    escaped.append(str(rel))
        raw_mcp = manifest.contains.get("mcp")
        if raw_mcp and resolve_within(manifest.path, raw_mcp) is None:
            escaped.append(str(raw_mcp))
        if escaped:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"contains path escapes the plugin directory; whole plugin rejected: {escaped}",
            )


__all__ = ["PluginInstaller"]
