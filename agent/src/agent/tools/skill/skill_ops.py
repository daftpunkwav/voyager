"""Skill operations shared by the skill capability and the skill tool (the
todowrite pattern): load reads one skill's full text, propose persists a new
or updated SKILL.md under the skills directory.

Validation lives here so the REST envelope (ServiceError) and the model
surface (readable [参数错误] text) cannot drift.
"""

from __future__ import annotations

import re
from pathlib import Path

from platform_contracts import ErrorSuffix, ServiceError

_MAX_NAME_LENGTH = 64
_MAX_DESC_CHARS = 2_000
_MAX_CONTENT_CHARS = 100_000
_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def load_skill_text(loader, name: str) -> dict:
    """Full text of one skill; KeyError (unapproved/deleted) -> NOT_FOUND."""
    try:
        text = loader.full_text(name)
    except KeyError:
        raise ServiceError("agent", ErrorSuffix.NOT_FOUND, f"no such skill: {name}") from None
    return {"name": name, "text": text}


def propose_skill(skills_dir: str | Path, name: str, description: str, content: str) -> dict:
    """Validate and persist one skill; the loader indexes it immediately."""
    clean_name = name.strip().lower()
    if len(clean_name) > _MAX_NAME_LENGTH:
        raise ServiceError(
            "agent",
            ErrorSuffix.INVALID_INPUT,
            f"skill name too long (max {_MAX_NAME_LENGTH} chars)",
        )
    if not _NAME_RE.match(clean_name):
        raise ServiceError(
            "agent",
            ErrorSuffix.INVALID_INPUT,
            f"invalid skill name: {name!r}",
            hint="use lowercase words joined by hyphens, e.g. python-recursion-guide",
        )
    clean_desc = description.strip()
    if not clean_desc:
        raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "description must not be empty")
    if len(clean_desc) > _MAX_DESC_CHARS:
        raise ServiceError(
            "agent",
            ErrorSuffix.INVALID_INPUT,
            f"description too long (max {_MAX_DESC_CHARS} chars)",
        )
    clean_content = content.strip()
    if not clean_content:
        raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "content must not be empty")
    if len(clean_content) > _MAX_CONTENT_CHARS:
        raise ServiceError(
            "agent", ErrorSuffix.INVALID_INPUT, f"content too long (max {_MAX_CONTENT_CHARS} chars)"
        )

    target_dir = Path(skills_dir) / clean_name
    target_dir.mkdir(parents=True, exist_ok=True)
    skill_file = target_dir / "SKILL.md"
    is_update = skill_file.exists()
    text = f"# {clean_name}\n\n{clean_desc}\n\n{clean_content}\n"
    try:
        skill_file.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise ServiceError(
            "agent", ErrorSuffix.CONFLICT, f"cannot write the skill file: {exc}"
        ) from None
    return {"name": clean_name, "updated": is_update, "path": str(skill_file)}


__all__ = ["load_skill_text", "propose_skill"]
