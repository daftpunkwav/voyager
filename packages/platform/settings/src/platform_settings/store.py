"""Settings persistence: SQLite-backed storage with validation, secret and
user_only write protection, and change events.

Responsibilities:
- register_fresh / list_schema: schema registration and rendering source
  for the settings page
- get / set: validated reads and protected writes (secrets writable by the
  user only; user_only restricted to the user)
- publish settings.changed on every successful write
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Self

from platform_contracts import (
    ActorKind,
    ActorRef,
    DomainEvent,
    ErrorSuffix,
    Event,
    ServiceError,
)
from platform_eventbus import EventBus

from platform_settings.define import SettingDef, SettingType, validate

_DOMAIN = "settings"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS setting_values (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    ts         REAL NOT NULL
);
"""


class SettingsStore:
    """Settings storage.

    defs are registered by services at startup (code side); values are
    persisted (data side). Single connection with one shared read/write lock
    (check_same_thread=False for cross-thread use).
    """

    def __init__(self, db_path: str | Path, bus: EventBus | None = None) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()
        self._bus = bus
        self._defs: dict[str, SettingDef] = {}

    def register(self, defs: Iterable[SettingDef]) -> None:
        # _defs shares the read/write lock with get/set: registration writes
        # and runtime reads may run concurrently on different threads
        with self._lock:
            for d in defs:
                if d.key in self._defs:
                    raise ServiceError(
                        _DOMAIN, ErrorSuffix.CONFLICT, f"duplicate setting registration: {d.key}"
                    )
                self._defs[d.key] = d

    def register_fresh(self, defs: Iterable[SettingDef]) -> int:
        """Idempotent registration: skip keys already registered (the
        convention when multiple services wire into a shared store)."""
        with self._lock:
            fresh = [d for d in defs if d.key not in self._defs]
            for d in fresh:
                self._defs[d.key] = d
        return len(fresh)

    def _def(self, key: str) -> SettingDef:
        try:
            return self._defs[key]
        except KeyError:
            raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"unknown setting: {key}") from None

    def get(self, key: str) -> Any:
        """Read the current value (default if unset). Internal callers may
        read the real value of secrets."""
        d = self._def(key)
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM setting_values WHERE key = ?", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else d.default

    async def set(self, key: str, value: Any, actor: ActorRef) -> None:
        """Write a setting: validate -> write protection (secrets hidden from
        non-users; user_only restricted to the user) -> persist -> publish a
        change event."""
        d = self._def(key)
        if actor.kind is not ActorKind.USER:
            if d.secret:
                raise ServiceError(
                    _DOMAIN,
                    ErrorSuffix.FORBIDDEN,
                    f"secret settings are writable by the user only: {key}",
                    hint="fill it in manually on the settings page",
                )
            if d.user_only:
                raise ServiceError(
                    _DOMAIN,
                    ErrorSuffix.FORBIDDEN,
                    f"this setting can be changed by the user only: {key}",
                    hint="security boundary for network/working directory/external services; change it on the settings page",
                )
        value = validate(d, value)

        def _write() -> None:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO setting_values (key, value, updated_by, ts) VALUES (?, ?, ?, ?)"
                    " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
                    " updated_by = excluded.updated_by, ts = excluded.ts",
                    (key, json.dumps(value, ensure_ascii=False), actor.id, time.time()),
                )
                self._conn.commit()

        await asyncio.to_thread(_write)
        if self._bus is not None:
            payload: dict[str, Any] = {"key": key, "module": d.module, "secret": d.secret}
            if not d.secret:
                payload["value"] = value
            await self._bus.publish(
                Event(type=DomainEvent.SETTINGS_CHANGED, actor=actor, payload=payload)
            )

    def list_schema(self) -> list[dict[str, Any]]:
        """Full settings schema (drives dynamic rendering of the settings page).

        Secret items never return values, only has_value.
        """
        out: list[dict[str, Any]] = []
        for key in sorted(self._defs):
            d = self._defs[key]
            with self._lock:
                row = self._conn.execute(
                    "SELECT value FROM setting_values WHERE key = ?", (key,)
                ).fetchone()
            item: dict[str, Any] = {
                "key": key,
                "module": d.module,
                "type": d.type.value,
                "description": d.description,
                "secret": d.secret,
                "choices": list(d.choices),
                "min": d.min,
                "max": d.max,
                "has_value": row is not None,
            }
            if not d.secret:
                item["default"] = d.default
                item["value"] = json.loads(row[0]) if row else d.default
            out.append(item)
        return out

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


__all__ = ["SettingDef", "SettingType", "SettingsStore", "validate"]
