"""Capability tests for the settings service: themes, aggregated schema,
secret boundary, change events.
"""

import pytest
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import ActorKind, ActorRef, ServiceError
from platform_settings import SettingDef, SettingType
from settings.capabilities import registry

USER_CTX = ActorContext(actor=ActorRef(kind=ActorKind.USER, id="user.local"))
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


class TestTheme:
    async def test_defaults(self, deps) -> None:
        out = await execute(registry, "get_theme", USER_CTX, {})
        # Factory default follows the system; explicit user light/dark wins afterwards.
        assert out == {"theme": "system", "font_scale": 1.0, "code_font": "JetBrains Mono"}

    async def test_list_themes(self, deps) -> None:
        out = await execute(registry, "list_themes", AGENT_CTX, {})
        assert [t["id"] for t in out] == ["dark", "light", "system"]

    async def test_agent_can_switch_theme(self, deps) -> None:
        """Whatever a user can change, an agent can change too (privacy excepted)."""
        _store, log = deps
        out = await execute(registry, "set_theme", AGENT_CTX, {"theme": "light", "font_scale": 1.2})
        assert out["theme"] == "light" and out["font_scale"] == 1.2
        changed = [e for _, e in log.read_after() if e.type == "settings.changed"]
        assert {e.payload["key"] for e in changed} == {"appearance.theme", "appearance.font_scale"}

    async def test_invalid_choice(self, deps) -> None:
        with pytest.raises(ServiceError) as ei:
            await execute(registry, "set_theme", USER_CTX, {"theme": "blue"})
        assert ei.value.body.code == "SETTINGS.INVALID_INPUT"

    async def test_empty_set_theme(self, deps) -> None:
        with pytest.raises(ServiceError) as ei:
            await execute(registry, "set_theme", USER_CTX, {})
        assert ei.value.body.code == "SETTINGS.INVALID_INPUT"


class TestLocale:
    """appearance.locale: the UI-language setting the web client watches."""

    async def test_default_zh_cn(self, deps) -> None:
        item = await execute(registry, "get_setting", USER_CTX, {"key": "appearance.locale"})
        assert item["value"] == "zh-CN"

    async def test_user_can_set_locale_and_event_emitted(self, deps) -> None:
        _store, log = deps
        out = await execute(
            registry, "set_setting", USER_CTX, {"key": "appearance.locale", "value": "en"}
        )
        assert out["value"] == "en"
        changed = [e for _, e in log.read_after() if e.type == "settings.changed"]
        assert any(
            e.payload["key"] == "appearance.locale" and e.payload["value"] == "en" for e in changed
        )

    async def test_system_choice_allowed(self, deps) -> None:
        out = await execute(
            registry, "set_setting", AGENT_CTX, {"key": "appearance.locale", "value": "system"}
        )
        assert out["value"] == "system"

    async def test_invalid_locale_rejected(self, deps) -> None:
        with pytest.raises(ServiceError) as ei:
            await execute(
                registry, "set_setting", USER_CTX, {"key": "appearance.locale", "value": "jp"}
            )
        assert ei.value.body.code == "SETTINGS.INVALID_INPUT"


class TestAggregation:
    async def test_cross_module_schema(self, deps) -> None:
        """With another service's defs registered, aggregation filters by module
        (dynamic settings-page rendering).
        """
        store, _ = deps
        store.register(
            [
                SettingDef(
                    key="notes.sort.default",
                    module="notes",
                    type=SettingType.CHOICE,
                    default="updated",
                    choices=("updated", "title"),
                )
            ]
        )
        all_items = await execute(registry, "get_settings", USER_CTX, {})
        assert {i["module"] for i in all_items} >= {"appearance", "privacy", "notes"}
        notes_only = await execute(registry, "get_settings", USER_CTX, {"module": "notes"})
        assert [i["key"] for i in notes_only] == ["notes.sort.default"]

    async def test_get_setting(self, deps) -> None:
        item = await execute(registry, "get_setting", AGENT_CTX, {"key": "privacy.activity_report"})
        assert item["value"] is True  # activity reporting is on by default

    async def test_unknown_key(self, deps) -> None:
        with pytest.raises(ServiceError) as ei:
            await execute(registry, "get_setting", USER_CTX, {"key": "nope.nope"})
        assert ei.value.body.code == "SETTINGS.NOT_FOUND"


class TestSecretBoundary:
    @pytest.fixture()
    async def secret_key(self, deps) -> str:
        store, _ = deps
        store.register(
            [
                SettingDef(
                    key="privacy.test_secret",
                    module="privacy",
                    type=SettingType.STR,
                    default="",
                    secret=True,
                )
            ]
        )
        return "privacy.test_secret"

    async def test_agent_write_secret_rejected(self, deps, secret_key) -> None:
        with pytest.raises(ServiceError) as ei:
            await execute(registry, "set_setting", AGENT_CTX, {"key": secret_key, "value": "x"})
        assert ei.value.body.code == "SETTINGS.FORBIDDEN"

    async def test_user_write_secret_then_mask(self, deps, secret_key) -> None:
        item = await execute(
            registry, "set_setting", USER_CTX, {"key": secret_key, "value": "plain-x"}
        )
        assert item["secret"] and item["has_value"]
        assert "value" not in item  # secret items never return the value
