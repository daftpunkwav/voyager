"""Settings for the office service, such as the export directory."""

from platform_settings import SettingDef, SettingType

DEFS = [
    SettingDef(
        key="office.export.dir",
        module="office",
        type=SettingType.STR,
        default="workspace/exports/",
        description="Default document export directory",
    ),
]
