"""Tests for secrets: roundtrip, key material sources, no-material
degradation, key listing.
"""

import pytest
from platform_secrets import SecretStore, SecretUnavailableError, load_key_material


class TestStore:
    def test_roundtrip(self, tmp_path) -> None:
        store = SecretStore(tmp_path / "s.db", key_material="test-material")
        store.set("llm.provider.openai.api_key", "sk-abc")
        assert store.get("llm.provider.openai.api_key") == "sk-abc"
        assert store.has("llm.provider.openai.api_key")
        # only ciphertext in the database
        raw = store._conn.execute("SELECT ciphertext FROM secrets").fetchone()[0]
        assert "sk-abc" not in raw
        store.close()

    def test_get_missing_returns_none(self, tmp_path) -> None:
        store = SecretStore(tmp_path / "s.db", key_material="m")
        assert store.get("nope") is None
        store.close()

    def test_wrong_material_reads_as_unset(self, tmp_path) -> None:
        SecretStore(tmp_path / "s.db", key_material="m1").set("k", "v")
        store = SecretStore(tmp_path / "s.db", key_material="m2")
        assert store.get("k") is None  # rotated key material reads as unset
        store.close()

    def test_unavailable_without_material(self, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv("SECRETS_ENCRYPTION_KEY", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        store = SecretStore(tmp_path / "s.db", key_material="")
        assert store.available is False
        with pytest.raises(SecretUnavailableError):
            store.set("k", "v")
        store.close()

    def test_keys_never_returns_values(self, tmp_path) -> None:
        store = SecretStore(tmp_path / "s.db", key_material="m")
        store.set("a", "1")
        store.set("b", "2")
        assert store.keys() == ["a", "b"]
        store.close()


class TestKeyMaterial:
    def test_env_primary_wins(self, monkeypatch) -> None:
        monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", "enc")
        monkeypatch.setenv("SECRET_KEY", "plain")
        assert load_key_material(env_file="nonexistent.env") == "enc"

    def test_example_material_rejected(self, monkeypatch) -> None:
        monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", "change-me-to-a-long-random-secret-key")
        monkeypatch.delenv("SECRET_KEY", raising=False)
        assert load_key_material(env_file="nonexistent.env") == ""

    def test_env_file_fallback(self, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv("SECRETS_ENCRYPTION_KEY", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        env = tmp_path / ".env"
        env.write_text('SECRETS_ENCRYPTION_KEY="from-file"\n', encoding="utf-8")
        assert load_key_material(env_file=env) == "from-file"

    def test_missing_env_file_yields_empty(self, tmp_path, monkeypatch) -> None:
        """No environment material and no env file: empty material, the caller
        decides (BYOK: secrets become unavailable)."""
        monkeypatch.delenv("SECRETS_ENCRYPTION_KEY", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        assert load_key_material(env_file=tmp_path / "absent.env") == ""

    def test_env_file_skips_comments_blank_and_keyless_lines(self, tmp_path, monkeypatch) -> None:
        """The .env scan tolerates comments, blank lines and malformed rows
        before finding the primary key."""
        monkeypatch.delenv("SECRETS_ENCRYPTION_KEY", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        env = tmp_path / ".env"
        env.write_text(
            "# comment line\n"
            "\n"
            "GARBAGE line without equals\n"
            "OTHER_KEY=noise\n"
            "SECRETS_ENCRYPTION_KEY = 'spaced-value'\n",
            encoding="utf-8",
            newline="\n",
        )
        assert load_key_material(env_file=env) == "spaced-value"

    def test_env_file_without_known_keys_yields_empty(self, tmp_path, monkeypatch) -> None:
        """A well-formed env file that names neither key yields no material."""
        monkeypatch.delenv("SECRETS_ENCRYPTION_KEY", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        env = tmp_path / ".env"
        env.write_text("OTHER_KEY=noise\nANOTHER=2\n", encoding="utf-8")
        assert load_key_material(env_file=env) == ""

    def test_env_file_secret_key_fallback(self, tmp_path, monkeypatch) -> None:
        """Without SECRETS_ENCRYPTION_KEY in file or environment, the file's
        SECRET_KEY is the second fallback (quotes stripped)."""
        monkeypatch.delenv("SECRETS_ENCRYPTION_KEY", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        env = tmp_path / ".env"
        env.write_text('SECRET_KEY="file-fallback-material"\n', encoding="utf-8")
        assert load_key_material(env_file=env) == "file-fallback-material"

    def test_env_secret_key_fallback_warns_on_short_material(
        self, tmp_path, monkeypatch, caplog
    ) -> None:
        """Short material is used (BYOK must not refuse service) but warns."""
        import logging

        monkeypatch.delenv("SECRETS_ENCRYPTION_KEY", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.setenv("SECRET_KEY", "short")
        with caplog.at_level(logging.WARNING, logger="platform.secrets"):
            material = load_key_material(env_file=tmp_path / "absent.env")
        assert material == "short"
        assert any("only 5 characters" in r.message for r in caplog.records)


class TestKdfMigration:
    """PBKDF2-derived key with a per-store salt: identical material no longer
    yields identical keys across installs, and legacy single-SHA-256 rows are
    re-encrypted in place on first read (kdf1: prefix, no downtime window)."""

    @staticmethod
    def _legacy_row(store: SecretStore, key: str, plain: str) -> None:
        """Write a row exactly as the pre-migration store would have."""
        import base64
        import hashlib

        from cryptography.fernet import Fernet

        digest = hashlib.sha256(b"old-material").digest()
        fernet = Fernet(base64.urlsafe_b64encode(digest))
        token = fernet.encrypt(plain.encode()).decode("ascii")
        with store._lock:
            store._conn.execute(
                "INSERT INTO secrets (key, ciphertext, updated_ts)"
                " VALUES (?, ?, strftime('%s','now'))",
                (key, token),
            )
            store._conn.commit()

    def test_new_write_uses_kdf1_prefix(self, tmp_path) -> None:
        store = SecretStore(tmp_path / "s.db", key_material="new-material")
        store.set("k", "v")
        raw = store._conn.execute("SELECT ciphertext FROM secrets WHERE key='k'").fetchone()[0]
        assert raw.startswith("kdf1:")
        store.close()

    def test_legacy_row_reads_and_migrates_in_place(self, tmp_path) -> None:
        store = SecretStore(tmp_path / "s.db", key_material="old-material")
        self._legacy_row(store, "k", "legacy-secret")
        assert store.get("k") == "legacy-secret"
        raw = store._conn.execute("SELECT ciphertext FROM secrets WHERE key='k'").fetchone()[0]
        assert raw.startswith("kdf1:")  # transparent rewrite happened
        assert store.get("k") == "legacy-secret"  # and still reads under the new KDF
        store.close()

    def test_legacy_row_wrong_material_reads_as_unset(self, tmp_path) -> None:
        store = SecretStore(tmp_path / "s.db", key_material="old-material")
        self._legacy_row(store, "k", "legacy-secret")
        store.close()
        other = SecretStore(tmp_path / "s.db", key_material="different")
        assert other.get("k") is None
        other.close()

    def test_same_material_different_stores_derive_different_keys(self, tmp_path) -> None:
        """The whole point of the salt: identical material on two installs
        produces ciphertext unreadable across stores."""
        a = SecretStore(tmp_path / "a.db", key_material="same")
        b = SecretStore(tmp_path / "b.db", key_material="same")
        a.set("k", "v")
        b.set("k", "v")
        raw_a = a._conn.execute("SELECT ciphertext FROM secrets WHERE key='k'").fetchone()[0]
        raw_b = b._conn.execute("SELECT ciphertext FROM secrets WHERE key='k'").fetchone()[0]
        assert raw_a != raw_b
        a.close()
        b.close()
