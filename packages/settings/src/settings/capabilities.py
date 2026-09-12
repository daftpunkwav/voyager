"""Capability registry for the settings service: theme controls
plus generic get/set/schema aggregation.

Responsibilities:
- Theme / font / code-font appearance controls (list/get/set_theme)
- Generic get_setting / set_setting over the shared SettingsStore, plus
  schema aggregation filtered by module (settings-page groups)
- Leave validation, secret write protection, and change events to the
  platform SettingsStore; get_setting returns only has_value for secrets

- Users and agents share the same capabilities (LocalAuth: empty scopes are
  allowed through);
- Write protection for secret items is enforced by the platform
  SettingsStore (non-user -> FORBIDDEN), and get_setting returns only
  has_value for secret items, never the value;
- After set_theme / set_setting persist, SettingsStore automatically emits
  settings.changed events that the web client watches for live updates.
"""

from __future__ import annotations

from dataclasses import dataclass

from platform_capability import Registry, capability
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, ServiceError
from platform_settings import SettingsStore

from .settings import DEFS, THEMES

_DOMAIN = "settings"
registry = Registry(_DOMAIN)

_THEME_LABELS = {"dark": "Dark", "light": "Light", "system": "Follow system"}


@dataclass
class Deps:
    store: SettingsStore


_deps: Deps | None = None


def init_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("deps not injected: call init_deps() at service entry first")
    return _deps


def _schema_item(key: str) -> dict:
    for item in _require_deps().store.list_schema():
        if item["key"] == key:
            return item
    raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"Unknown setting key: {key}")


@capability(registry, name="list_themes", description="Available theme list", cost=1)
def list_themes() -> list[dict]:
    return [{"id": t, "label": _THEME_LABELS[t]} for t in THEMES]


@capability(
    registry,
    name="get_theme",
    description="Current appearance settings (theme/font scale/code font)",
    cost=1,
)
def get_theme() -> dict:
    store = _require_deps().store
    return {
        "theme": store.get("appearance.theme"),
        "font_scale": store.get("appearance.font_scale"),
        "code_font": store.get("appearance.code_font"),
    }


@capability(
    registry,
    name="set_theme",
    description="Switch theme/font scale/code font (can run silently)",
    cost=1,
)
async def set_theme(
    theme: str | None = None,
    font_scale: float | None = None,
    code_font: str | None = None,
    _actor: ActorRef | None = None,
) -> dict:
    if theme is None and font_scale is None and code_font is None:
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            "at least one of theme / font_scale / code_font is required",
        )
    store = _require_deps().store
    actor = _actor or ActorRef(kind=ActorKind.SYSTEM, id="settings.service")
    if theme is not None:
        await store.set("appearance.theme", theme, actor)
    if font_scale is not None:
        await store.set("appearance.font_scale", font_scale, actor)
    if code_font is not None:
        await store.set("appearance.code_font", code_font, actor)
    return get_theme()


@capability(
    registry,
    name="get_settings",
    description="Aggregated settings schema for all modules (filterable by group)",
    cost=1,
)
def get_settings(module: str | None = None) -> list[dict]:
    items = _require_deps().store.list_schema()
    if module:
        items = [i for i in items if i["module"] == module]
    return items


@capability(
    registry,
    name="get_setting",
    description="Read one setting item (secret items return has_value only)",
    cost=1,
)
def get_setting(key: str) -> dict:
    return _schema_item(key)


@capability(
    registry,
    name="set_setting",
    description="Write one setting item (secret items are user-writable only)",
    cost=1,
)
async def set_setting(key: str, value, _actor: ActorRef | None = None) -> dict:
    store = _require_deps().store
    actor = _actor or ActorRef(kind=ActorKind.SYSTEM, id="settings.service")
    # validation, secret write protection, and change events are the store's job
    await store.set(key, value, actor)
    return _schema_item(key)


__all__ = ["DEFS", "Deps", "init_deps", "registry"]
