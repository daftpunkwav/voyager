"""Secret storage: Fernet-encrypted at rest; plaintext is only ever returned
to in-process callers.

- Storage is a dedicated secrets namespace table, independent of any
  settings JSON blob.
- Only ciphertext is stored; `get` returns `None` for keys that were never
  set (missing key material raises `SecretUnavailableError` instead).
- Key material never enters the database or logs.
- The key is derived with PBKDF2-HMAC-SHA256 (per-store random salt,
  persisted alongside the ciphertext) instead of a bare hash, so identical
  material no longer yields identical keys across installs and weak
  passphrases resist precomputation. Rows still encrypted under the legacy
  single-SHA-256 derivation are re-encrypted transparently on first read
  (``kdf1:`` prefix marks the new format), so migration is gradual with no
  downtime window.
"""

from __future__ import annotations

import base64
import hashlib
import os
import sqlite3
import threading
from pathlib import Path
from typing import Self

from cryptography.fernet import Fernet, InvalidToken

from platform_secrets.key_material import load_key_material

_SCHEMA = """
CREATE TABLE IF NOT EXISTS secrets (
    key        TEXT PRIMARY KEY,
    ciphertext TEXT NOT NULL,
    updated_ts REAL NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE TABLE IF NOT EXISTS secrets_kdf (
    id         INTEGER PRIMARY KEY CHECK (id = 0),
    salt       BLOB    NOT NULL,
    iterations INTEGER NOT NULL
);
"""

#: Format marker for ciphertext produced under the PBKDF2 derivation; the
#: Fernet token itself starts with \x80, so the prefix cannot collide.
_KDF_PREFIX = "kdf1:"

#: PBKDF2 parameters: the iteration count is the brute-force cost; the salt
#: only has to defeat precomputation/rainbow tables, so it needs no secrecy.
_KDF_ITERATIONS = 600_000


def _legacy_fernet_for(material: str) -> Fernet:
    """The retired single-SHA-256 derivation: kept only to decrypt rows that
    predate the PBKDF2 migration (re-encrypted on first read)."""
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class SecretUnavailableError(RuntimeError):
    """Raised when no key material is configured: the secrets feature is
    unavailable (BYOK flows should show onboarding guidance)."""


class SecretStore:
    """Single connection with one shared read/write lock
    (check_same_thread=False for cross-thread use); Fernet encryption at rest."""

    def __init__(self, db_path: str | Path, *, key_material: str | None = None) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._material = key_material if key_material is not None else load_key_material()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()
        self._fernet_instance: Fernet | None = None

    @property
    def available(self) -> bool:
        return bool(self._material)

    def _kdf_params(self) -> tuple[bytes, int]:
        """Per-store salt, created once and persisted next to the ciphertext;
        the iteration count is stored so a future raise can still decrypt.
        Caller holds self._lock (the lock is non-reentrant)."""
        row = self._conn.execute("SELECT salt, iterations FROM secrets_kdf WHERE id = 0")
        existing = row.fetchone()
        if existing is None:
            salt = os.urandom(16)
            self._conn.execute(
                "INSERT INTO secrets_kdf (id, salt, iterations) VALUES (0, ?, ?)",
                (salt, _KDF_ITERATIONS),
            )
            self._conn.commit()
            return salt, _KDF_ITERATIONS
        return bytes(existing[0]), int(existing[1])

    def _fernet(self) -> Fernet:
        if not self._material:
            raise SecretUnavailableError(
                "no key material configured: set SECRETS_ENCRYPTION_KEY (or SECRET_KEY)"
            )
        # The 600k-round derivation runs once per store (startup cost of a
        # few hundred ms), never on the hot get() path. Under the same lock
        # as _kdf_params: concurrent first reads must derive exactly once.
        with self._lock:
            if self._fernet_instance is None:
                salt, iterations = self._kdf_params()
                digest = hashlib.pbkdf2_hmac(
                    "sha256", self._material.encode("utf-8"), salt, iterations, dklen=32
                )
                self._fernet_instance = Fernet(base64.urlsafe_b64encode(digest))
            return self._fernet_instance

    def set(self, key: str, plain: str) -> None:
        token = self._fernet().encrypt(plain.encode("utf-8")).decode("ascii")
        ciphertext = _KDF_PREFIX + token
        with self._lock:
            self._conn.execute(
                "INSERT INTO secrets (key, ciphertext, updated_ts)"
                " VALUES (?, ?, strftime('%s','now'))"
                " ON CONFLICT(key) DO UPDATE SET ciphertext=excluded.ciphertext,"
                " updated_ts=excluded.updated_ts",
                (key, ciphertext),
            )
            self._conn.commit()

    def get(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT ciphertext FROM secrets WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        fernet = self._fernet()  # raises SecretUnavailableError when unconfigured
        ciphertext = row[0]
        if not ciphertext.startswith(_KDF_PREFIX):
            # Legacy entry: encrypted under the old single-SHA-256 derivation.
            # Decrypt with the legacy key, then transparently re-encrypt under
            # the current KDF so migration is gradual and needs no downtime.
            try:
                plain = _legacy_fernet_for(self._material).decrypt(ciphertext.encode("ascii"))
            except (InvalidToken, ValueError):
                return None  # key material rotated: treat as unset, user re-enters
            try:
                plain_text = plain.decode("utf-8")
            except UnicodeDecodeError:
                return None
            self.set(key, plain_text)
            return plain_text
        try:
            return fernet.decrypt(ciphertext[len(_KDF_PREFIX) :].encode("ascii")).decode("utf-8")
        except InvalidToken:
            return None  # key material rotated: treat as unset, user re-enters

    def has(self, key: str) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT 1 FROM secrets WHERE key = ?", (key,)).fetchone()
        return row is not None

    def delete(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM secrets WHERE key = ?", (key,))
            self._conn.commit()

    def keys(self) -> list[str]:
        """List key names only, never values (for audits / settings UI has_value)."""
        with self._lock:
            rows = self._conn.execute("SELECT key FROM secrets ORDER BY key").fetchall()
        return [r[0] for r in rows]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
