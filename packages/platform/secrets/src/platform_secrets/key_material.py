"""Key material resolution: SECRETS_ENCRYPTION_KEY -> SECRET_KEY
-> repo-root .env.

- Results are not cached: key material may be reloaded explicitly (tests can
  inject their own).
- Environment variables take priority; the .env file is only a fallback and
  never overrides the environment.
- An empty return leaves the decision to the caller: under BYOK, no material
  means secrets are unavailable.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

ENV_PRIMARY = "SECRETS_ENCRYPTION_KEY"
ENV_FALLBACK = "SECRET_KEY"

_MIN_MATERIAL_LEN = 16
# Documented example value: long enough but publicly known; treated as
# unset so a copy-pasted example cannot decrypt the store.
_EXAMPLE_MATERIALS = frozenset(
    {
        "change-me-to-a-long-random-secret-key",
    }
)

log = logging.getLogger("platform.secrets")


def _pick(enc_key: str | None, secret_key: str | None) -> str:
    custom = (enc_key or "").strip()
    return custom if custom else (secret_key or "").strip()


def load_key_material(env_file: str | Path | None = None) -> str:
    """Load key material. An explicit env_file takes priority over probing
    the default repo-root .env.

    Material shorter than 16 characters logs a warning instead of refusing
    service: under BYOK, refusing would suddenly break every existing
    secret; the warning prompts the user to switch to stronger material.
    """
    material = _pick(os.environ.get(ENV_PRIMARY), os.environ.get(ENV_FALLBACK))
    if not material:
        path = Path(env_file) if env_file else _repo_env()
        material = _read_from_env_file(path)
    if material in _EXAMPLE_MATERIALS:
        log.warning("refusing documented example key material; set a random %s", ENV_PRIMARY)
        return ""
    if material and len(material) < _MIN_MATERIAL_LEN:
        log.warning(
            "key material is only %d characters (recommended >=%d): weak Fernet "
            "derivation; set a longer %s / %s",
            len(material),
            _MIN_MATERIAL_LEN,
            ENV_PRIMARY,
            ENV_FALLBACK,
        )
    return material


def _read_from_env_file(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == ENV_PRIMARY:
            return value.strip().strip('"').strip("'")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and line.partition("=")[0].strip() == ENV_FALLBACK:
            return line.partition("=")[2].strip().strip('"').strip("'")
    return ""


def _repo_env() -> Path | None:
    """Locate the repo-root .env: this package lives at
    packages/platform/secrets/src/platform_secrets/, so five levels up is the
    repo root.

    Limitation: relies on the repository layout (editable/source checkout).
    Non-source installs (e.g. sdist into site-packages) resolve a wrong
    "repo root"; a missing .env then yields empty material and the caller
    degrades gracefully — a known and accepted assumption for a local tool.
    """
    root = Path(__file__).resolve().parents[5]
    return root / ".env"
