"""Setting definitions for this service (via the platform/settings
framework).

At startup the service registers DEFS into the SettingsStore; the
settings page renders the group dynamically from the schema.
"""

from platform_settings import SettingDef, SettingType

DEFS = [
    SettingDef(
        key="template.worker.concurrency",
        module="template",
        type=SettingType.INT,
        default=1,
        min=1,
        max=8,
        description="Long-task worker concurrency",
    ),
]
