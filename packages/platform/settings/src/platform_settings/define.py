"""Setting definitions and value validation.

Responsibilities:
- SettingDef schema: key, type, default, choices/bounds, secret and
  user_only marking
- validate: coerce and range-check a value against its definition
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from platform_contracts import ErrorSuffix, ServiceError

_DOMAIN = "settings"
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")  # <module>.<name>[.<sub>]


class SettingType(str, Enum):
    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    CHOICE = "choice"
    JSON = "json"


@dataclass(frozen=True)
class SettingDef:
    """Setting declaration.

    Values of secret=True settings never appear in list_schema or event
    payloads; user_only=True settings are writable by the user only
    (preventing privilege escalation through settings), but their values
    are still echoed back.
    """

    key: str
    module: str
    type: SettingType
    default: Any = None
    description: str = ""
    secret: bool = False
    user_only: bool = False
    choices: tuple[Any, ...] = ()
    min: float | None = None
    max: float | None = None

    def __post_init__(self) -> None:
        if not _KEY_RE.match(self.key):
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.INVALID_INPUT,
                f"setting key must be dotted lowercase <module>.<name>: {self.key!r}",
            )


def validate(d: SettingDef, value: Any) -> Any:
    """Validate a value against the definition and return the normalized
    value; invalid values raise SETTINGS.INVALID_INPUT."""
    t = d.type
    ok = True
    if t is SettingType.BOOL:
        ok = isinstance(value, bool)
    elif t is SettingType.INT:
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif t is SettingType.FLOAT:
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        if ok:
            value = float(value)
    elif t in (SettingType.STR, SettingType.CHOICE):
        ok = isinstance(value, str)
    elif t is SettingType.JSON:
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            ok = False
    if not ok:
        raise ServiceError(
            _DOMAIN, ErrorSuffix.INVALID_INPUT, f"setting {d.key} should be of type {t.value}"
        )
    if t is SettingType.CHOICE and value not in d.choices:
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            f"setting {d.key} value must be one of {list(d.choices)}",
        )
    if t in (SettingType.INT, SettingType.FLOAT):
        if d.min is not None and value < d.min:
            raise ServiceError(
                _DOMAIN, ErrorSuffix.INVALID_INPUT, f"setting {d.key} cannot be less than {d.min}"
            )
        if d.max is not None and value > d.max:
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.INVALID_INPUT,
                f"setting {d.key} cannot be greater than {d.max}",
            )
    return value
