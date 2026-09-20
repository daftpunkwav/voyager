# plugins — plugin discovery, approval, and declarative loading

A plugin is a plugin-root subdirectory with a `plugin.json` manifest declaring skills / hooks / mcp entries; plugins never import platform code and no plugin script is ever executed. The pipeline is discover, then user approval, then declarative load (skills into the SkillLoader, hooks into the HookRegistry, MCP entries registered as pending — tools are never auto-approved). The `PluginManager` is assembled by `build.py` onto `AgentApp` and surfaced to humans and agent alike through the extension capability.

## Files

- manager.py — `PluginManager`: discovery, approval persistence (`agent.plugins.approved` / `agent.plugins.approvals`, user_only, mutually exclusive on write), idempotent load/unload, event-subscription push to the event loop after every change; MCP reclamation on revoke only touches entries with no approved tools
- manifest.py — pure shape layer: `PluginManifest`, `discover()`, `load_manifest()` parsing `plugin.json` / `mcp.json` / approval data; no runtime state
- install.py — file-movement primitives: safe zip extraction (zip-root convention, 20 MiB archive / 500 files / 5 MiB per file caps, zip-slip rejection), directory-source validation, placement on disk
- installer.py — install/uninstall policy on top of install.py: the source must be exactly one of `zip_path` / `source_dir` resolving inside allowed roots; `copytree` into `plugins/<name>/` happens only after manifest, name, jail, and conflict validation; uninstall removes unapproved plugins only
- effects.py — stateless side-effect policies split from the manager: external MCP pending-entry registration and safety-chain reclamation, and event-subscription retention while a pattern is still needed by other approved plugins or user hooks

## Notes

- `__init__.py` re-exports `PluginManager`, `PluginManifest`, `discover`, `load_manifest`, `APPROVED_KEY`, `APPROVALS_KEY`.
- Loading is hot: approval or revocation takes effect without a restart.
