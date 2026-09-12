"""Domain constants for the notes service (single source of truth).

DOMAIN lives in this leaf module so that validate.py and store.py can both
import it top-level without creating an import cycle between runtime,
store, and validate.
"""

DOMAIN = "notes"
