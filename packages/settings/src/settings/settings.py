"""Setting definitions owned by the settings service: appearance /
interaction / privacy.

Each item's module field names its settings-page group. SettingDefs of other
services (notes/graph/llm/agent...) are declared in their own settings.py and
registered into the same platform SettingsStore; this service aggregates the
output by module.
"""

from platform_settings import SettingDef, SettingType

THEMES = ("dark", "light", "system")
LOCALES = ("zh-CN", "en", "system")

DEFS = [
    # Appearance
    SettingDef(
        key="appearance.theme",
        module="appearance",
        type=SettingType.CHOICE,
        default="system",
        choices=THEMES,
        description="UI theme",
    ),
    SettingDef(
        key="appearance.locale",
        module="appearance",
        type=SettingType.CHOICE,
        default="zh-CN",
        choices=LOCALES,
        description="UI locale",
    ),
    SettingDef(
        key="appearance.font_scale",
        module="appearance",
        type=SettingType.FLOAT,
        default=1.0,
        min=0.8,
        max=1.5,
        description="Global font scale",
    ),
    SettingDef(
        key="appearance.code_font",
        module="appearance",
        type=SettingType.STR,
        default="JetBrains Mono",
        description="Code font",
    ),
    # Interaction (arbitration mode / quiet hours / reach budget live under
    # agent.* keys in the agent service defs; not re-declared here to avoid
    # dual-source drift)
    # Privacy
    SettingDef(
        key="privacy.activity_report",
        module="privacy",
        type=SettingType.BOOL,
        default=True,
        description="Allow reporting page/focus activity signals for agent observation",
    ),
]
