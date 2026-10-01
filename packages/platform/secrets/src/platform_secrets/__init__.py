"""Secret custody: encrypted storage and on-demand distribution.

The store performs no actor checks itself; the "user writes secrets"
rule is enforced one layer up, by the capabilities that expose secret
writes (they reject non-USER actors before calling set()).
"""

from platform_secrets.key_material import load_key_material
from platform_secrets.store import SecretStore, SecretUnavailableError

__all__ = ["SecretStore", "SecretUnavailableError", "load_key_material"]
