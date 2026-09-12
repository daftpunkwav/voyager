"""Composition-root setting definitions.

Host is not a scanned domain. Its SettingDefs still register into the shared
store so the settings page can render them and so assembly can read an
explicit domain whitelist without an environment variable.
"""

from __future__ import annotations

from platform_settings import SettingDef, SettingType

DEFS = [
    SettingDef(
        key="host.domains.enabled",
        module="host",
        type=SettingType.JSON,
        default=[],
        user_only=True,
        description=(
            "When non-empty, overrides the module cards' enabled_by_default: "
            "only these domain names get wired; an empty list keeps each "
            "card's default. The ENABLE_DOMAINS env var wins over this setting."
        ),
    ),
]
