# platform/settings — Settings framework

Each setting is defined by: `key / type / default / owning module / secret flag / description` (§7.9).

- Each service declares its own settings in its `settings.py` and calls `register()` at startup;
- `set()` validates type/value domain; **secret items are writable by the user only** (§8.8 privacy exception);
- Changes publish a `settings.changed` event (secret item payloads carry no value);
- `list_schema()` lets the settings page render dynamically: no setting is hardcoded, and secrets only return `has_value`.

---

## Purpose

Settings store: typed SettingDef registry (STR/INT/FLOAT/BOOL/JSON), hot-read values, change events, user_only + secret enforcement.

## Configuration

None — every module registers its own defs (register_fresh is idempotent).

## Extension Points

Register SettingDefs in your module; never read unregistered keys (get raises NOT_FOUND).

## Known Limitations

user_only is all-or-nothing per key (no scopes).

## Deferred Work

Per-key actor scopes.
