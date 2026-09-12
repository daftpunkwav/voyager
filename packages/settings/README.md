# settings

> Not to be confused with `packages/platform/settings` (the settings *framework*:
> store, schema registry, user_only enforcement). This package is the settings
> *domain* on top of that framework.

## Purpose

Settings domain: REST/bridge access to the shared settings store plus theme keys.

## Configuration

Owns theme.* keys; all other modules register their defs into the same store.

## Extension Points

Nothing to extend here — register SettingDefs in your own module.

## Model Experience

Tools: settings__get_settings / set_setting. user_only keys reject agent actors at the settings layer.

## Known Limitations

No schema versioning/migrations.

## Deferred Work

Per-key change permissions beyond user_only.
