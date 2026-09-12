"""Sources service setting definitions (rendered dynamically by the
settings page).
"""

from platform_settings import SettingDef, SettingType

DEFS = [
    SettingDef(
        key="sources.sort.default",
        module="sources",
        type=SettingType.CHOICE,
        default="added",
        choices=("added", "updated", "title"),
        description="Default library sort field",
    ),
    SettingDef(
        key="sources.import.clone",
        module="sources",
        type=SettingType.BOOL,
        default=True,
        description="Clone repos locally on import (otherwise only metadata is stored)",
    ),
    SettingDef(
        key="sources.doc.max_file_mb",
        module="sources",
        type=SettingType.INT,
        default=200,
        min=1,
        max=2000,
        description="Max size per imported document (MB)",
    ),
]
