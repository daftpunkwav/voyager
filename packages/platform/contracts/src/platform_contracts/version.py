"""Protocol versions.

Bump PROTOCOL_VERSION on protocol changes; during multi-version coexistence
the generators emit both versions.
"""

PROTOCOL_VERSION = "0.1.0"

# Envelope structure version (bump when the field set changes)
ENVELOPE_VERSION = 1
