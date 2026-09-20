"""Shell dimension: destructive/skills/read-root guards and the decision
function (split from policy.engine, phase 21).

The confirm era is over: every command executes unless a guard hard-rejects
(skills subtree, read-only roots) — the reported default level stays L2 for
intent visibility, but invoke.py no longer confirms it. Bash command-prefix
rules live in the permission resolver (policy/permissions.py, "bash:" deny /
allow entries), which reuses command_tokens/_matches_prefix from here.
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
    """Shell dimension knobs: the reported default level (L2, see module
    docstring — invoke.py no longer confirms it). The command-prefix
    allow/deny rules retired with the confirm channel."""

    level: Level = Level.L2_CONFIRM


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


def _strip_token_quotes(token: str) -> str:
    """Drop one pair of wrapping quotes shlex keeps in posix=False mode: without
    this, `"git" push` would tokenize as ('"git"', 'push') and slip past a
    `bash:git push` deny prefix."""
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    return token


def command_tokens(cmd: str) -> tuple[str, ...]:
    """Parse a command into tokens for prefix matching; an unparseable
    command yields no tokens, so it can never match a rule (falls back to
    the default level). posix=False everywhere: matching is best-effort and
    platform-consistent, not execution (run_shell owns execution).

    Tokens are unquoted and case-folded so quoting shapes and Windows'
    case-insensitive resolution cannot dodge a deny prefix; the folded case
    can only over-match on case-sensitive platforms (the safe direction)."""
    try:
        raw = shlex.split(cmd or "", posix=False)
    except ValueError:
        return ()
    return tuple(_strip_token_quotes(t).lower() for t in raw)


def _exe_free(token: str) -> str:
    """Strip a trailing `.exe` so the first token compares as the binary name
    (`git.exe push` must not dodge a `bash:git push` deny prefix on Windows)."""
    return token.removesuffix(".exe")


def _matches_prefix(tokens: tuple[str, ...], pattern: str) -> bool:
    parts = pattern.lower().split()
    if not parts:
        return False
    if parts == ["*"]:
        return True
    if not tokens:
        return False
    head = parts[:-1] if parts[-1] == "*" else parts
    if len(tokens) < len(head) or (parts[-1] != "*" and len(tokens) != len(head)):
        return False
    # Executable-name normalization applies to the first token only: later
    # arguments like `setup.exe` are ordinary file names.
    return _exe_free(tokens[0]) == _exe_free(head[0]) and tokens[1 : len(head)] == tuple(head[1:])


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
    return Decision(True, shell.level, "command execution (no confirm; guards above still apply)")


__all__ = ["ShellPolicy", "decide_shell"]
