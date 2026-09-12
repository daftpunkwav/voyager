"""Shell dimension: destructive/skills/read-root guards and the decision
function (split from policy.engine, phase 21). Everything defaults to L2 —
command execution is confirmed by a human unless a remembered approval
(ApprovalStore) says otherwise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from agent.policy.decision import Decision
from agent.policy.levels import Level

# Copy/move/delete verb list, shared by the skills guard and the read-only-roots guard so
# the two cannot drift
_SHELL_WRITE_VERBS = r"cp|mv|move|copy|xcopy|rm|del|erase|rd|rmdir|unlink|touch|tee"

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
    """Shell dimension is level-driven (L2 by default); the dataclass exists
    so the engine carries one snapshot like every other dimension."""

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


def decide_shell(fs, shell_level: Level, action) -> Decision:
    # skills subtree must not be rewritten via shell: reject before L2 (as the fs check does)
    if (action.write or action.irreversible) and _targets_skills_write(action.target):
        return Decision(False, reason="skill directory cannot be modified via shell")
    # Read-only additional roots must not be rewritten via shell (closing a shell bypass):
    # likewise rejected before L2; paths inside write_roots are not blocked (consistent
    # with the fs dimension, still L2). Additional roots are hot-read, sharing the same
    # source as fs decisions.
    if (action.write or action.irreversible) and _targets_read_root_write(
        action.target, fs.read_roots, fs.write_roots
    ):
        return Decision(False, reason="read-only additional roots cannot be modified via shell")
    return Decision(True, shell_level, "Command execution requires confirmation by default")


__all__ = ["ShellPolicy", "decide_shell"]
