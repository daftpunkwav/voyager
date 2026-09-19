"""Action levels: L0 silent / L1 notify / L2 confirm. Config may only
tighten, never loosen.
"""

from enum import IntEnum


class Level(IntEnum):
    L0_SILENT = 0  # execute silently, audit only
    L1_NOTIFY = 1  # execute and notify the user
    L2_CONFIRM = 2  # confirmation requested; honored only for write_roots writes (confirm retired elsewhere)
