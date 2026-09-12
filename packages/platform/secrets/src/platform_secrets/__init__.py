"""Secret custody: encrypted storage and on-demand distribution.

Only the user themselves may write secrets.
"""

from platform_secrets.key_material import load_key_material
from platform_secrets.store import SecretStore, SecretUnavailableError

__all__ = ["SecretStore", "SecretUnavailableError", "load_key_material"]
