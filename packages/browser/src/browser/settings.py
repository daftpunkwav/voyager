"""Settings for the browser service: headless mode and allowed
domains.
"""

from platform_settings import SettingDef, SettingType

DEFS = [
    SettingDef(
        key="browser.headless",
        module="browser",
        type=SettingType.BOOL,
        default=True,
        description="Whether to run the browser headless",
    ),
    SettingDef(
        key="browser.allowed_domains",
        module="browser",
        type=SettingType.JSON,
        default=[],
        description="Domain allowlist for automation (empty = inherit agent network permissions)",
    ),
]
