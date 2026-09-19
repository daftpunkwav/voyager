"""Shell dimension: destructive/skills/read-root guards and the decision
function (split from policy.engine, phase 21). The default level stays L2 as
the reported intent, but the confirm dialog is retired: invoke.py executes
unless the decision carries confirm_scope="write_roots". Command-prefix
allow/deny rules are confirm-era leftovers — the deny list is superseded by
the permission resolver's bash: entries (kept until the cleanup phase).
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from agent.policy.decision import Decision
from agent.policy.levels import Level

# Copy/move/delete verb list, shared by the skills guard and the read-only-roots guard so
# the two cannot drift. dd/chmod/chown/truncate/rsync are write-shaped the same way; they
# are rare in read-only commands, so their false-positive cost is an L2 fallback only.
_SHELL_WRITE_VERBS = (
    r"cp|mv|move|copy|xcopy|rm|del|erase|rd|rmdir|unlink|touch|tee|dd|chmod|chown|truncate|rsync"
)

# Write-capable flags: a prefix allow rule may cover a command whose WRITE
# side happens entirely in a flag (`git diff --output=x`, `find -delete`,
# `sort -o out`, `dd of=`) - none of these carry a verb or a `>` character.
# The allow gate refuses these tokens so "read-only convenience" rules cannot
# launder flag-carried writes; false positives (e.g. `grep -o`) only fall
# back to the default L2 confirm, never to a denial.
_WRITE_FLAG_EXACT = frozenset({"-o", "-O", "-delete", "--backup", "--in-place", "-inplace"})
_WRITE_FLAG_PREFIXES = ("--output", "of=", "--out-file")

# Shell-dimension skills write ban (closing a shell bypass): a conservative regex that spots
# literals clearly writing into / deleting from the skills subtree, without full shell
# parsing -- prefer missing exotic variants (e.g. py -c inline file writes) over false
# positives on read-only commands like grep skills/README or type skills\keep\SKILL.md.
# Path segments allow ./ ../ and ordinary segment prefixes (repo/../skills still resolves
# into skills); a separator is required to avoid matching same-prefixed names like
# skills.txt or skills_backup.
_SKILLS_PATH = r"(?:(?:\.{1,2}|[\w.-]+)[/\\])*skills[/\\]"
# Branch 1: redirection (> / >> / 2>) into skills; branch 2: copy/move/delete verb + skills path
_SHELL_SKILLS_WRITE_RE = re.compile(
    r">>?\s*['\"]?"
    + _SKILLS_PATH
    + r"|\b(?:"
    + _SHELL_WRITE_VERBS
    + r")\b"
    + r"[^|;&>\n]*"
    + _SKILLS_PATH,
    re.IGNORECASE,
)

# Shell-dimension guard for read-only additional roots (closing a shell bypass): conservative
# detection in the same spirit as the skills guard, no full shell parsing -- complex variants
# (py -c inline writes, variable-built paths) may slip through.
# Paths inside write_roots are treated as writable and not blocked (consistent with the fs
# dimension, still going through L2); relative paths use the workspace as cwd and naturally
# land inside the jail, so they never reach this function (skills still go through the
# skills guard).
# Coarse write/delete intent filter: branch 1 is redirection (> / >> / 2>) targeting an
# absolute path; branch 2 is the presence of a verb from the verb list.
_SHELL_WRITE_INTENT_RE = re.compile(
    r">>?\s*['\"]?(?:[A-Za-z]:[/\\]|/)|\b(?:" + _SHELL_WRITE_VERBS + r")\b",
    re.IGNORECASE,
)
# Absolute path literals in the command (Windows drive letters / Unix root); truncated by
# quotes, whitespace, pipes, semicolons, redirection
_SHELL_ABS_PATH_RE = re.compile(r"[A-Za-z]:[/\\][^\s|;&\"']*|/[^\s|;&\"']*")


@dataclass(frozen=True)
class ShellPolicy:
    """Shell dimension: default level (L2 confirms every command), plus
    command-prefix allow/deny rules.

    Rules are token prefixes of the parsed command: `git status` matches only
    exactly that command; a trailing `*` (`git diff *`) matches the head plus
    any remaining arguments; the bare `*` matches everything. Deny wins over
    allow. An allow hit still falls back to the default level when the
    command carries write intent (verbs / redirection) - prefix rules are a
    convenience for read-only commands, never a write bypass.
    """

    level: Level = Level.L2_CONFIRM
    allowed: frozenset[str] = frozenset()
    denied: frozenset[str] = frozenset()


def _targets_skills_write(cmd: str) -> bool:
    """Whether the command string clearly writes into / deletes from the skills subtree
    (conservative detection)."""
    return bool(_SHELL_SKILLS_WRITE_RE.search(cmd or ""))


def _targets_read_root_write(
    cmd: str, read_roots: tuple[str, ...], write_roots: tuple[str, ...]
) -> bool:
    """Whether the command string clearly writes into / deletes from a read-only additional
    root (conservative detection).

    A coarse intent pre-filter runs first (redirection or copy/move/delete verbs); on a hit,
    absolute path literals are extracted from the command and resolved one by one: a path
    under some read-only root and under no read-write root returns True (should be rejected,
    before L2). Paths also under a read-write root are treated as writable (same root order
    as _decide_fs)."""
    if not _SHELL_WRITE_INTENT_RE.search(cmd or ""):
        return False
    for raw in _SHELL_ABS_PATH_RE.findall(cmd or ""):
        target = Path(raw).resolve()
        writable = False
        for root in write_roots:  # read-write roots outrank read-only roots (same order as fs)
            root_path = Path(root).resolve()
            if target == root_path or root_path in target.parents:
                writable = True
                break
        if writable:
            continue
        for root in read_roots:
            root_path = Path(root).resolve()
            if target == root_path or root_path in target.parents:
                return True
    return False


def command_tokens(cmd: str) -> tuple[str, ...]:
    """Parse a command into tokens for prefix matching; an unparseable
    command yields no tokens, so it can never match a rule (falls back to
    the default level). posix=False everywhere: matching is best-effort and
    platform-consistent, not execution (run_shell owns execution)."""
    try:
        return tuple(shlex.split(cmd or "", posix=False))
    except ValueError:
        return ()


def _matches_prefix(tokens: tuple[str, ...], pattern: str) -> bool:
    parts = pattern.split()
    if not parts:
        return False
    if parts == ["*"]:
        return True
    if parts[-1] == "*":
        head = parts[:-1]
        return len(tokens) >= len(head) and tokens[: len(head)] == tuple(head)
    return tokens == tuple(parts)


def _matches_any(tokens: tuple[str, ...], patterns: frozenset[str]) -> bool:
    return any(_matches_prefix(tokens, p) for p in patterns)


def _has_write_flag(tokens: tuple[str, ...]) -> bool:
    """Whether any non-command token is a known write-capable flag; see the
    gate comment at _WRITE_FLAG_EXACT for why this exists."""
    for tok in tokens[1:]:
        t = tok.lower()
        if t in _WRITE_FLAG_EXACT or t.startswith(_WRITE_FLAG_PREFIXES):
            return True
    return False


def decide_shell(fs, shell: ShellPolicy, action) -> Decision:
    cmd = action.target or ""
    # skills subtree must not be rewritten via shell: reject before L2 (as the fs check does)
    if (action.write or action.irreversible) and _targets_skills_write(cmd):
        return Decision(False, reason="skill directory cannot be modified via shell")
    # Read-only additional roots must not be rewritten via shell (closing a shell bypass):
    # likewise rejected before L2; paths inside write_roots are not blocked (consistent
    # with the fs dimension, still L2). Additional roots are hot-read, sharing the same
    # source as fs decisions.
    if (action.write or action.irreversible) and _targets_read_root_write(
        cmd, fs.read_roots, fs.write_roots
    ):
        return Decision(False, reason="read-only additional roots cannot be modified via shell")
    tokens = command_tokens(cmd)
    if tokens:  # unparseable/empty commands never match a rule: fall to L2
        if _matches_any(tokens, shell.denied):
            return Decision(False, reason=f"command matches a shell deny rule: {cmd.split()[0]}…")
        if (
            _matches_any(tokens, shell.allowed)
            and not _SHELL_WRITE_INTENT_RE.search(cmd)
            and ">" not in cmd
            and not _has_write_flag(tokens)
        ):
            return Decision(
                True, Level.L0_SILENT, "allowed by shell prefix rule: read-only command"
            )
    return Decision(True, shell.level, "Command execution requires confirmation by default")


__all__ = ["ShellPolicy", "decide_shell"]
