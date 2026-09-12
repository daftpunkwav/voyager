"""Plugin manifest and approval shapes (pure shape layer split out of
manager.py).

Only parsing/validation from plugin.json / mcp.json / approval data into
structured shapes; no runtime state, no MCP client access. Orchestration
(load, approval persistence, install placement) stays in manager.py;
manifest format changes only touch this file.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from platform_contracts import ErrorSuffix, ServiceError

log = logging.getLogger("agent.plugins.manifest")


@dataclass(frozen=True)
class Approval:
    """One effective approval selection: per group, (all-selected flag, names)."""

    skills_all: bool = False
    skills: frozenset[str] = frozenset()  # skill names
    hooks_all: bool = False
    hooks: frozenset[str] = frozenset()  # hook file relative paths
    mcp_all: bool = False
    mcp: frozenset[str] = frozenset()  # server ids from mcp.json

    @property
    def empty(self) -> bool:
        """No group selected (empty submission; rejected on item approval so a
        recorded name never ends up loading nothing)."""
        return not (
            self.skills_all
            or self.skills
            or self.hooks_all
            or self.hooks
            or self.mcp_all
            or self.mcp
        )


#: Bundle = all three groups selected (MCP still only registers; tools are
#: never auto-approved)
BUNDLE = Approval(skills_all=True, hooks_all=True, mcp_all=True)


@dataclass(frozen=True)
class PluginManifest:
    """Parsed plugin.json; permissions / contains keep their raw shape."""

    name: str
    version: str
    description: str
    permissions: dict
    contains: dict
    path: Path  # plugin directory (absolute)


def load_manifest(plugin_dir: Path) -> PluginManifest | None:
    """Parse a single plugin.json; bad JSON / non-dict / missing name -> None
    (callers skip; boot never breaks).

    A missing plugin.json is a normal scan skip and stays silent; parse
    failures / bad shapes / missing name indicate a broken plugin and are
    logged (previously silently None, which left nothing to debug from).
    """
    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("plugin %s plugin.json unparseable, skipped: %s", plugin_dir.name, exc)
        return None
    if not isinstance(data, dict):
        log.warning("plugin %s plugin.json must be an object, skipped", plugin_dir.name)
        return None
    name = str(data.get("name") or "").strip()
    if not name:
        log.warning("plugin %s plugin.json missing the name field, skipped", plugin_dir.name)
        return None
    permissions = data.get("permissions")
    contains = data.get("contains")
    return PluginManifest(
        name=name,
        version=str(data.get("version") or ""),
        description=str(data.get("description") or ""),
        permissions=permissions if isinstance(permissions, dict) else {},
        contains=contains if isinstance(contains, dict) else {},
        path=plugin_dir,
    )


def discover(root: str | Path) -> list[PluginManifest]:
    """Scan every subdirectory of root that has a plugin.json (sorted by
    directory name; `_`-prefixed included, broken ones excluded)."""
    base = Path(root)
    if not base.is_dir():
        return []
    out: list[PluginManifest] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        manifest = load_manifest(child)
        if manifest is not None:
            out.append(manifest)
    return out


def resolve_within(base: Path, rel: object) -> Path | None:
    """contains relative path -> absolute path; None for empty strings or
    escapes from base (``../``, absolute paths) - the path jail."""
    text = str(rel or "").strip()
    if not text:
        return None
    candidate = (base / text).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        return None
    return candidate


def normalize_items(raw: object) -> list[object]:
    """Normalize contains entries: strings and lists both become lists."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw.strip():
        return [raw]
    return []


def parse_choice(raw: object, field: str) -> tuple[bool, set[str]]:
    """Normalize per-item input: (True, empty) = "*" selects all;
    (False, names) = explicit name list.

    None -> (False, empty) = group not involved (nothing loads, nothing is
    skipped); list elements must be non-empty strings, otherwise
    INVALID_INPUT (dirty types are never silently treated as empty).
    """
    if raw is None:
        return False, set()
    if raw == "*":
        return True, set()
    if isinstance(raw, list):
        bad = [x for x in raw if not isinstance(x, str) or not x.strip()]
        if bad:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"{field} must be '*' or a list of non-empty names, got: {bad!r}",
            )
        return False, {str(x) for x in raw}
    raise ServiceError(
        "agent",
        ErrorSuffix.INVALID_INPUT,
        f"{field} must be '*' or a name list: {raw!r}",
    )


def parse_approval(raw: object) -> Approval | None:
    """Persisted approvals[name] -> Approval; malformed shapes (non-dict /
    invalid values) -> None (treated as unapproved)."""
    if not isinstance(raw, dict):
        return None
    try:
        skills_all, skills = parse_choice(raw.get("skills"), "skills")
        hooks_all, hooks = parse_choice(raw.get("hooks"), "hooks")
        mcp_all, mcp = parse_choice(raw.get("mcp"), "mcp")
    except ServiceError:
        return None
    return Approval(
        skills_all=skills_all,
        skills=frozenset(skills),
        hooks_all=hooks_all,
        hooks=frozenset(hooks),
        mcp_all=mcp_all,
        mcp=frozenset(mcp),
    )


def manifest_skills(manifest: PluginManifest) -> list[Path]:
    """Directories under contains.skills that really contain a SKILL.md
    (entries outside the jail are dropped)."""
    out: list[Path] = []
    for rel in normalize_items(manifest.contains.get("skills")):
        path = resolve_within(manifest.path, rel)
        if path is not None and (path / "SKILL.md").is_file():
            out.append(path)
    return out


def manifest_skill_entries(manifest: PluginManifest) -> list[tuple[Path, str]]:
    """List of (skill dir, skill name); same rule as SkillLoader._scan
    (SKILL.md parent directory name).

    Per-item selection is by skill name; duplicate names across directories
    are all listed and all add_root-ed at load time (plugin authors must
    keep names unique; one contains entry is usually a single-skill root).
    """
    out: list[tuple[Path, str]] = []
    for skill_dir in manifest_skills(manifest):
        for name in skill_names_in(skill_dir):
            out.append((skill_dir, name))
    return out


def manifest_hook_entries(manifest: PluginManifest) -> list[tuple[Path, str]]:
    """List of (hook json absolute path, declared relative path); the relative
    path is the per-item selection id (multiple files may share one on)."""
    out: list[tuple[Path, str]] = []
    for rel in normalize_items(manifest.contains.get("hooks")):
        text = str(rel or "").strip()
        if not text:
            continue
        path = resolve_within(manifest.path, text)
        if path is not None and path.is_file():
            out.append((path, text))
    return out


def manifest_mcp(manifest: PluginManifest) -> Path | None:
    """Path to a real mcp.json under contains.mcp; None when undeclared or
    missing."""
    path = resolve_within(manifest.path, manifest.contains.get("mcp"))
    if path is not None and path.is_file():
        return path
    return None


def manifest_mcp_servers(manifest: PluginManifest) -> dict[str, dict]:
    """Servers dict parsed from mcp.json; {} when missing / bad / empty."""
    path = manifest_mcp(manifest)
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    servers = data.get("servers") if isinstance(data, dict) else None
    return servers if isinstance(servers, dict) else {}


def skill_names_in(skill_dir: Path) -> list[str]:
    """Skill names in a directory (same rule as SkillLoader._scan: the
    SKILL.md parent directory name)."""
    return [p.parent.name for p in sorted(skill_dir.rglob("SKILL.md"))]


def hook_on(hook_path: Path) -> str:
    """The on declared by a hook json; empty string for bad files (display
    skips, never raises)."""
    try:
        data = json.loads(hook_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(data.get("on") or "") if isinstance(data, dict) else ""


def hook_enabled(hook_path: Path) -> bool:
    """Whether a hook json is enabled; False for bad files."""
    try:
        data = json.loads(hook_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(data.get("enabled", False)) if isinstance(data, dict) else False
