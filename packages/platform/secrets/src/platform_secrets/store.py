"""Secret storage: Fernet-encrypted at rest; plaintext is only ever returned
to in-process callers.

- Storage is a dedicated secrets namespace table, independent of any
  settings JSON blob.
- Only ciphertext is stored; `get` returns `None` instead of raising, which
  makes "not configured" easy to express.
- Key material never enters the database or logs.
- The ciphertext format stays compatible with the legacy store: values
  encrypted under the same key material remain readable.
"""

from __future__ import annotations

import base64
import hashlib
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
"""


def _fernet_for(material: str) -> Fernet:
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

    @property
    def available(self) -> bool:
        return bool(self._material)

    def _fernet(self) -> Fernet:
        if not self._material:
            raise SecretUnavailableError(
                "no key material configured: set SECRETS_ENCRYPTION_KEY (or SECRET_KEY)"
            )
        return _fernet_for(self._material)

    def set(self, key: str, plain: str) -> None:
        ciphertext = self._fernet().encrypt(plain.encode("utf-8")).decode("ascii")
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
        try:
            return self._fernet().decrypt(row[0].encode("ascii")).decode("utf-8")
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
