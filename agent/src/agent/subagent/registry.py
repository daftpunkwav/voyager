"""Registration and loading of user-defined subagents.

Definitions live in data/runtime/subagents/*.json; the master looks them up
by name when dispatching. Users can customize: mode, persona, capability
surface (allowed tools), permission tier (scopes), and trigger style.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from platform_contracts import ErrorSuffix, ServiceError

from agent.policy.network import NET_ALL, NET_OFF, NET_WHITELIST
from agent.subagent.modes import Mode

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_DOMAIN = "agent"
_NETWORK_MODES = ("", NET_OFF, NET_WHITELIST, NET_ALL)  # empty = inherit global


def _safe_name(name: str) -> str:
    """Names go straight into file paths, so validate here (blocks ../ escapes
    out of the subagents directory)."""
    if not _NAME_RE.match(name):
        raise ServiceError(
            _DOMAIN, ErrorSuffix.INVALID_INPUT, f"name must be lowercase snake_case: {name}"
        )
    return name


@dataclass(frozen=True)
class SubagentDef:
    name: str
    description: str
    mode: str = "react"
    persona: str = ""  # persona preset key (may be empty)
    allowed_tools: tuple[str, ...] | None = None  # None = no trimming
    #: Read-only definition: the spawned instance additionally loses every
    #: write/irreversible tool (default-deny review bots).
    readonly: bool = False
    scopes: tuple[str, ...] = ()
    trigger: str = "manual"  # manual | event:<pattern>
    max_rounds: int | None = None  # ReAct round override; None = follow global
    max_tool_calls: int | None = None  # tool-call limit override; None = follow global
    network_mode: str = ""  # network tier override; empty = inherit global

    def __post_init__(self) -> None:
        _safe_name(self.name)
        valid_modes = {m.value for m in Mode}
        if self.mode not in valid_modes:
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.INVALID_INPUT,
                f"unknown mode: {self.mode} (valid: {sorted(valid_modes)})",
            )
        if self.network_mode not in _NETWORK_MODES:
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.INVALID_INPUT,
                f"unknown network mode: {self.network_mode} (valid: off/whitelist/all, empty inherits global)",
            )
        for field_name in ("max_rounds", "max_tool_calls"):
            value = getattr(self, field_name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
            ):
                raise ServiceError(
                    _DOMAIN,
                    ErrorSuffix.INVALID_INPUT,
                    f"{field_name} must be a positive integer or unset (follows global)",
                )
        # After a JSON round-trip lists must be normalized back to tuples
        # (frozen dataclass, so via object.__setattr__)
        object.__setattr__(self, "scopes", tuple(self.scopes))
        if self.allowed_tools is not None:
            object.__setattr__(self, "allowed_tools", tuple(self.allowed_tools))
        if not isinstance(self.readonly, bool):
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.INVALID_INPUT,
                "readonly must be a boolean",
            )


class SubagentRegistry:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, d: SubagentDef) -> Path:
        path = self._root / f"{d.name}.json"
        path.write_text(json.dumps(asdict(d), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load(self, name: str) -> SubagentDef:
        name = _safe_name(name)
        path = self._root / f"{name}.json"
        if not path.exists():
            raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"unregistered subagent: {name}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return SubagentDef(**data)

    def list(self) -> list[SubagentDef]:
        """Registered definitions; a single corrupt or invalid file is skipped
        without blocking other entries or list_subagents."""
        out: list[SubagentDef] = []
        for p in sorted(self._root.glob("*.json")):
            try:
                out.append(SubagentDef(**json.loads(p.read_text(encoding="utf-8"))))
            except (
                json.JSONDecodeError,
                UnicodeDecodeError,
                ValueError,
                KeyError,
                TypeError,
                OSError,
                ServiceError,
            ):
                continue
        return out

    def delete(self, name: str) -> None:
        name = _safe_name(name)
        (self._root / f"{name}.json").unlink(missing_ok=True)
