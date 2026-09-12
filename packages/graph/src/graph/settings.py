"""Settings for the graph service: engine selection, queue
concurrency, retries.
"""

from platform_settings import SettingDef, SettingType

#: Default address of the C engine sidecar (single source of truth;
#: rest.py / wiring.py default params reference this).
DEFAULT_C_URL = "http://127.0.0.1:8123"

DEFS = [
    SettingDef(
        key="graph.engine.mode",
        module="graph",
        type=SettingType.CHOICE,
        default="auto",
        choices=("auto", "c", "python"),
        description="Graph engine: auto = prefer C with automatic fallback to Python; can be forced",
    ),
    SettingDef(
        key="graph.engine.c_url",
        module="graph",
        type=SettingType.STR,
        default=DEFAULT_C_URL,
        description="C engine sidecar address (build artifact of engines/c/core)",
    ),
    SettingDef(
        key="graph.index.concurrency",
        module="graph",
        type=SettingType.INT,
        default=1,
        min=1,
        max=4,
        description="Max index concurrency",
    ),
    SettingDef(
        key="graph.index.max_attempts",
        module="graph",
        type=SettingType.INT,
        default=3,
        min=1,
        max=10,
        description="Max retries after index failure",
    ),
    SettingDef(
        key="graph.query.default_limit",
        module="graph",
        type=SettingType.INT,
        default=200,
        min=10,
        max=10000,
        description="Default row limit for graph queries",
    ),
]
