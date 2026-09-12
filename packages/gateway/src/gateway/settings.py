"""Gateway service setting definitions.

The gateway process has no business database; these values are read by
the deployment entry point (composition root) from the shared
SettingsStore and injected as create_app parameters. Only the schema is
declared here so the settings page can render the "gateway" group
dynamically.
"""

from platform_settings import SettingDef, SettingType

DEFS = [
    SettingDef(
        key="gateway.rate_limit.per_minute",
        module="gateway",
        type=SettingType.INT,
        default=600,
        min=10,
        max=100000,
        description="Max requests per actor per minute",
    ),
    SettingDef(
        key="gateway.sse.max_connections",
        module="gateway",
        type=SettingType.INT,
        default=8,
        min=1,
        max=128,
        description="Max concurrent SSE connections",
    ),
    SettingDef(
        key="gateway.chat.history_page_size",
        module="gateway",
        type=SettingType.INT,
        default=200,
        min=20,
        max=2000,
        description="Chat history entries fetched per request",
    ),
]
