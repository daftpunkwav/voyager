"""Filesystem dimension: jail roots ordering and the decision function.

Root priority: workspace roots (L2 on delete, skills subtree hard-no-write)
> additional read-write roots (L2 on write/delete) > additional read-only
roots (writes always rejected, before any confirmation).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent.policy.decision import Decision
from agent.policy.levels import Level


@dataclass(frozen=True)
class FsPolicy:
    roots: tuple[str, ...] = ("data/workspace",)  # fs jail roots
    read_roots: tuple[str, ...] = ()  # additional read-only roots: reads pass, writes rejected
    write_roots: tuple[str, ...] = ()  # additional read-write roots: reads L0, writes/deletes L2


def decide_fs(fs: FsPolicy, action) -> Decision:
    target = Path(action.target)
    if not target.is_absolute() and fs.roots:
        target = Path(fs.roots[0]) / target  # resolved against the jail root (as fs tools do)
    target = target.resolve()
    for root in fs.roots:
        root_path = Path(root).resolve()
        if target == root_path or root_path in target.parents:
            if action.write or action.irreversible:
                # skills directory is write/delete protected: if SKILL.md were writable, a
                # prompt injection would enter the "available skills" index the next turn;
                # the rejection must happen in this check, before L2 confirmation (a delete
                # should not first ask "allow deletion?" and then fail)
                reserved = root_path / "skills"
                if target == reserved or reserved in target.parents:
                    return Decision(
                        False, reason="skill directory cannot be modified via file tools"
                    )
            if action.irreversible:
                return Decision(True, Level.L2_CONFIRM, "Deletion requires confirmation")
            return Decision(True, Level.L1_NOTIFY if action.write else Level.L0_SILENT)
    # Additional read-write roots: user-configured writable whitelist directories, reads
    # L0, writes/deletes L2 confirmation. Checked before read_roots: a path under both a
    # read-write root and a read-only root is treated as writable. The skills write ban is
    # not re-checked here -- it belongs to the workspace jail only (handled inside the
    # roots loop above), and write_roots cannot bypass it.
    for root in fs.write_roots:
        root_path = Path(root).resolve()
        if target == root_path or root_path in target.parents:
            if action.irreversible:
                return Decision(
                    True,
                    Level.L2_CONFIRM,
                    "Deletion in a user directory requires confirmation",
                    confirm_scope="write_roots",
                )
            if action.write:
                return Decision(
                    True,
                    Level.L2_CONFIRM,
                    "Writes to a user directory require confirmation",
                    confirm_scope="write_roots",
                )
            return Decision(True, Level.L0_SILENT)
    # Outside the workspace jail and read-write roots: additional read-only roots allow
    # reads only; writes/deletes are always rejected (before L2 -- additional roots get no
    # delete confirmation, since confirming would not grant write access anyway). The
    # skills special case needs no extra check: additional roots already reject writes.
    # roots take priority over read_roots: the workspace and its subtree are exempt from
    # additional-root read-only constraints.
    for root in fs.read_roots:
        root_path = Path(root).resolve()
        if target == root_path or root_path in target.parents:
            if action.write or action.irreversible:
                return Decision(
                    False,
                    reason=f"Additional root is read-only; writes/deletes are limited to the working directory: {target}",
                )
            return Decision(True, Level.L0_SILENT)
    return Decision(False, reason=f"Path outside the working directory: {target} (fs jail)")


__all__ = ["FsPolicy", "decide_fs"]
