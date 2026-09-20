"""Tool-surface permission modes: one mode + two lists, default full.

The single gate in front of every native tool invocation (wired in
tools.core.invoke): the mode constrains agent actors only — humans reach the
same operations through capability REST endpoints, which never pass through
this resolver. Domain bridge tools (notes__*) and mcp__* tools declare no
class: they count as D (fail-closed), so read_only / no_dangerous cover the
whole surface with no loophole.

Storage: the `agent.permissions` setting (user_only — the agent cannot raise
its own privileges through the settings bridge), hot-read on every call,
never cached. Shape:

    {"mode": "full", "deny": ["write", "session.delete", "bash:git push*"],
     "allow": ["bash"]}

- mode: full | no_dangerous | read_only (default full)
- deny entries: "tool" | "tool.action" | "bash:<command prefix>" (argv
  prefix, applied after the mode lets bash through — effective in every
  mode)
- allow entries: same syntax; consulted only in no_dangerous (read_only is
  a hard ceiling)

Malformed values degrade independently: an unknown mode reads as full and
unparsable list entries are skipped, so a corrupt value falls back to the
factory default instead of bricking the agent.

The class table is the single source of truth for R/D. P1 keys are the flat
tool names; the surface aggregation (P3) re-keys entries to "tool.action"
with the tool-level entry as the default — one table, one system.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent.policy.shell import _matches_prefix, command_tokens

FULL, NO_DANGEROUS, READ_ONLY = "full", "no_dangerous", "read_only"
MODES = (FULL, NO_DANGEROUS, READ_ONLY)

#: Factory default of the agent.permissions setting: everything allowed, no
#: deny entries. settings.py imports this for the SettingDef default so the
#: resolver and the registered default cannot drift apart.
PERMISSIONS_DEFAULT = {"mode": FULL, "deny": [], "allow": []}

CLASS_R, CLASS_D = "R", "D"

#: Single source of truth: tool -> R (read-only class) | D (dangerous class).
#: Absent = unknown = D (fail-closed). P3 aggregation re-keys to "tool.action"
#: (exact action keys take precedence over the tool-level default).
TOOL_CLASS: dict[str, str] = {
    # workspace hands
    "read": CLASS_R,
    "grep": CLASS_R,
    "glob": CLASS_R,
    "write": CLASS_D,
    "edit": CLASS_D,
    "bash": CLASS_D,
    "todowrite": CLASS_R,
    # interaction
    "ask_user": CLASS_R,
    "request_context": CLASS_R,
    "reach_out": CLASS_R,
    # plan / scratchpad / goals (main-goal guardrails live in the dispatch
    # rules, not in permissions)
    "scratchpad": CLASS_R,
    "goal_read": CLASS_R,
    "goal_write": CLASS_R,
    "exit_plan_mode": CLASS_R,
    # context window
    "context_status": CLASS_R,
    "compact_context": CLASS_R,
    # network
    "web_fetch": CLASS_R,
    "web_search": CLASS_R,
    # session surface (aggregated; delete is the one irreversible action)
    "session": CLASS_R,
    "session.delete": CLASS_D,
    # observation (aggregated; events/quota) and tool self-management
    "observe": CLASS_R,
    "tools": CLASS_R,
    "activate_tools": CLASS_R,
    # jobs (aggregated): observing/reordering is R, cancelling loses work
    "jobs": CLASS_R,
    "jobs.cancel": CLASS_D,
    # memory (aggregated): reads R, persistent writes D
    "memory": CLASS_R,
    "memory.remember": CLASS_D,
    "memory.forget": CLASS_D,
    "memory.clear": CLASS_D,
    # skills
    "load_skill": CLASS_R,
    "propose_skill": CLASS_R,
    # extension: lists/previews R, lifecycle D
    "list_plugins": CLASS_R,
    "install_plugin": CLASS_D,
    "uninstall_plugin": CLASS_D,
    "list_mcp_servers": CLASS_R,
    "preview_mcp_tools": CLASS_R,
    "list_user_hooks": CLASS_R,
    "reload_user_hooks": CLASS_D,
    # team: spawn inherits the parent surface (R); register/unregister reshape
    # the shared roster; run control splits on reversible vs work-losing
    "spawn_subagent": CLASS_R,
    "list_subagents": CLASS_R,
    "wait_subagent": CLASS_R,
    "register_subagent": CLASS_D,
    "delete_subagent": CLASS_D,
    "read_board": CLASS_R,
    "write_board": CLASS_R,
    "pause_run": CLASS_R,
    "resume_run": CLASS_R,
    "list_resumable_checkpoints": CLASS_R,
    "cancel_run": CLASS_D,
    "abandon_resumable_checkpoint": CLASS_D,
}


def tool_class(name: str, action: str | None = None) -> str:
    """Class of one tool (optionally one action): exact "tool.action" key
    first, then the tool-level default; anything unknown is D."""
    if action:
        cls = TOOL_CLASS.get(f"{name}.{action}")
        if cls in (CLASS_R, CLASS_D):
            return cls
    return TOOL_CLASS.get(name, CLASS_D)


@dataclass(frozen=True)
class _PermissionRules:
    """Parsed view of one agent.permissions value."""

    mode: str = FULL
    deny: frozenset[str] = frozenset()
    allow: frozenset[str] = frozenset()
    bash_deny_prefixes: tuple[str, ...] = ()
    bash_allow_prefixes: tuple[str, ...] = ()


def _normalize_bash_pattern(pattern: str) -> str:
    """Normalize one bash prefix pattern to the token-prefix grammar the
    shell policy matches with: the trailing `*` must stand alone as the final
    token (`git push*` and `git push *` are the same pattern; an attached
    star is not a token suffix)."""
    p = pattern.strip()
    if p.endswith("*"):
        head = p[:-1].strip()
        return f"{head} *" if head else "*"
    return p


def _split_entries(entries: list[str]) -> tuple[frozenset[str], tuple[str, ...]]:
    """Split raw list entries into (tool/tool.action names, bash command
    prefixes); non-string entries are skipped."""
    names: set[str] = set()
    bash: list[str] = []
    for entry in entries:
        if not isinstance(entry, str) or not entry:
            continue
        if entry.startswith("bash:"):
            pattern = entry[len("bash:") :].strip()
            if pattern:
                bash.append(_normalize_bash_pattern(pattern))
        else:
            names.add(entry)
    return frozenset(names), tuple(bash)


def _parse_rules(raw: object) -> _PermissionRules:
    """Parse the stored JSON; every field degrades independently."""
    if not isinstance(raw, dict):
        return _PermissionRules()
    mode = raw.get("mode")
    if mode not in MODES:
        mode = FULL

    def _list(key: str) -> list[str]:
        value = raw.get(key)
        return [e for e in value if isinstance(e, str)] if isinstance(value, list) else []

    deny_names, bash_deny = _split_entries(_list("deny"))
    allow_names, bash_allow = _split_entries(_list("allow"))
    return _PermissionRules(
        mode=mode,
        deny=deny_names,
        allow=allow_names,
        bash_deny_prefixes=bash_deny,
        bash_allow_prefixes=bash_allow,
    )


class ToolPermissions:
    """Agent-actor tool gate: one mode + two lists, hot-read per call."""

    def __init__(self, settings) -> None:  # SettingsStore handle (anything with .get)
        self._settings = settings

    def _rules(self) -> _PermissionRules:
        try:
            raw = self._settings.get("agent.permissions")
        except Exception:  # noqa: BLE001  # unregistered read (NOT_FOUND) or store failure
            return _PermissionRules()
        rules = _parse_rules(raw)
        # Legacy merge (replaces a write-migration): pre-modes installs could
        # store `agent.shell.denied` command prefixes; they apply as bash argv
        # deny prefixes in every mode, merged at read time so the effect is
        # identical to having migrated the entries into the deny list. The
        # legacy key retires with the confirm-era plumbing (cleanup phase).
        try:
            legacy = self._settings.get("agent.shell.denied")
        except Exception:  # noqa: BLE001  # unregistered (NOT_FOUND) or store failure
            legacy = None
        if isinstance(legacy, list) and legacy:
            merged = list(rules.bash_deny_prefixes)
            for entry in legacy:
                if isinstance(entry, str) and entry.strip():
                    pattern = _normalize_bash_pattern(entry)
                    if pattern not in merged:
                        merged.append(pattern)
            rules = _PermissionRules(
                mode=rules.mode,
                deny=rules.deny,
                allow=rules.allow,
                bash_deny_prefixes=tuple(merged),
                bash_allow_prefixes=rules.bash_allow_prefixes,
            )
        return rules

    def check(self, tool_name: str, arguments: object) -> str | None:
        """Resolve one agent tool call; None = allowed, otherwise a
        model-actionable rejection stating that this is user policy."""
        rules = self._rules()
        action = arguments.get("action") if isinstance(arguments, dict) else None
        action = action if isinstance(action, str) and action else None
        tokens: tuple[str, ...] | None = None
        if tool_name == "bash" and (rules.bash_deny_prefixes or rules.bash_allow_prefixes):
            command = arguments.get("command") if isinstance(arguments, dict) else None
            tokens = command_tokens(command if isinstance(command, str) else "")

        # 1-3: deny wins in every mode (action level, tool level, argv prefix)
        if action and f"{tool_name}.{action}" in rules.deny:
            return _denied(tool_name, action)
        if tool_name in rules.deny:
            return _denied(tool_name, action)
        if tokens is not None and any(_matches_prefix(tokens, p) for p in rules.bash_deny_prefixes):
            return _denied(tool_name, action)

        # 4: full mode — the deny list above is the only gate
        if rules.mode == FULL:
            return None

        cls = tool_class(tool_name, action)
        if rules.mode == READ_ONLY:
            # hard ceiling: the allow list is not consulted
            if cls == CLASS_R:
                return None
            return _denied(tool_name, action)

        # no_dangerous: allow hit (same syntax and precedence as deny), then
        # the R class; D and unknown tools are rejected
        if tool_name in rules.allow:
            return None
        if action and f"{tool_name}.{action}" in rules.allow:
            return None
        if tokens is not None and any(
            _matches_prefix(tokens, p) for p in rules.bash_allow_prefixes
        ):
            return None
        if cls == CLASS_R:
            return None
        return _denied(tool_name, action)


def _denied(tool_name: str, action: str | None) -> str:
    """Rejection text: readable, states whose policy it is, offers the fix."""
    what = f"{tool_name}.{action}" if action else tool_name
    return (
        f"[权限拒绝] {what} 被用户的工具权限策略拒绝(设置 → 工具权限)。"
        "这是用户策略而非故障:请改用允许的工具完成目标,或直接告知用户调整配置。"
    )


__all__ = [
    "CLASS_D",
    "CLASS_R",
    "FULL",
    "MODES",
    "NO_DANGEROUS",
    "PERMISSIONS_DEFAULT",
    "READ_ONLY",
    "TOOL_CLASS",
    "ToolPermissions",
    "tool_class",
]
