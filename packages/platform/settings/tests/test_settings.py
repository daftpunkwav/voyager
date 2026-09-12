"""Tests for settings: defaults, validation, secret/user_only protection,
events, schema.
"""

import pytest
from platform_contracts import ActorKind, ActorRef, DomainEvent, ServiceError
from platform_eventbus import EventBus, EventLog
from platform_settings import SettingDef, SettingsStore, SettingType

USER = ActorRef(kind=ActorKind.USER, id="local")
AGENT = ActorRef(kind=ActorKind.AGENT, id="agent.main")
SYSTEM = ActorRef(kind=ActorKind.SYSTEM, id="test")

DEFS = [
    SettingDef(
        key="agent.rounds.max", module="agent", type=SettingType.INT, default=20, min=1, max=200
    ),
    SettingDef(
        key="agent.arbiter.mode",
        module="agent",
        type=SettingType.CHOICE,
        default="queue",
        choices=("auto", "queue", "guide"),
    ),
    SettingDef(
        key="agent.network.mode",
        module="agent",
        type=SettingType.CHOICE,
        default="whitelist",
        choices=("off", "whitelist", "all"),
        user_only=True,
    ),
    SettingDef(key="ui.theme", module="ui", type=SettingType.STR, default="dark"),
    SettingDef(key="llm.kimi.api_key", module="llm", type=SettingType.STR, default="", secret=True),
]


@pytest.fixture()
def store(tmp_path):
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    st = SettingsStore(tmp_path / "settings.db", bus=bus)
    st.register(DEFS)
    yield st, log
    st.close()
    log.close()


class TestBasics:
    def test_default(self, store) -> None:
        st, _ = store
        assert st.get("agent.rounds.max") == 20

    async def test_set_get_and_persist(self, store, tmp_path) -> None:
        st, _ = store
        await st.set("ui.theme", "light", USER)
        assert st.get("ui.theme") == "light"
        reopened = SettingsStore(tmp_path / "settings.db")
        reopened.register(DEFS)
        assert reopened.get("ui.theme") == "light"  # persisted across reopen
        reopened.close()

    def test_unknown_key(self, store) -> None:
        st, _ = store
        with pytest.raises(ServiceError, match="unknown setting"):
            st.get("nope.key")

    def test_duplicate_register(self, store) -> None:
        st, _ = store
        with pytest.raises(ServiceError, match="duplicate setting registration"):
            st.register(DEFS)

    def test_register_fresh_idempotent(self, store) -> None:
        """Shared-store scenario: duplicate registration only adds new keys,
        existing ones are untouched."""
        st, _ = store
        assert st.register_fresh(DEFS) == 0  # all registered: idempotent skip
        extra = SettingDef(
            key="notes.sort.default", module="notes", type=SettingType.STR, default="updated"
        )
        assert st.register_fresh([*DEFS, extra]) == 1
        assert st.get("notes.sort.default") == "updated"


class TestValidation:
    async def test_type_check(self, store) -> None:
        st, _ = store
        with pytest.raises(ServiceError, match="of type int"):
            await st.set("agent.rounds.max", True, USER)

    async def test_range_check(self, store) -> None:
        st, _ = store
        with pytest.raises(ServiceError, match="cannot be greater than 200"):
            await st.set("agent.rounds.max", 999, USER)

    async def test_choice_check(self, store) -> None:
        st, _ = store
        with pytest.raises(ServiceError, match="must be one of"):
            await st.set("agent.arbiter.mode", "yolo", USER)
        await st.set("agent.arbiter.mode", "auto", USER)
        assert st.get("agent.arbiter.mode") == "auto"


class TestSecret:
    async def test_agent_write_forbidden(self, store) -> None:
        st, _ = store
        with pytest.raises(ServiceError) as exc:
            await st.set("llm.kimi.api_key", "sk-xxx", AGENT)
        assert exc.value.body.code == "SETTINGS.FORBIDDEN"
        assert exc.value.http_status == 403

    async def test_user_write_ok_and_schema_redacted(self, store) -> None:
        st, _ = store
        await st.set("llm.kimi.api_key", "sk-xxx", USER)
        schema = {item["key"]: item for item in st.list_schema()}
        secret_item = schema["llm.kimi.api_key"]
        assert secret_item["has_value"] is True
        assert "value" not in secret_item  # secret values are never returned
        theme = schema["ui.theme"]
        assert theme["value"] == "dark"

    async def test_change_event_omits_secret_value(self, store) -> None:
        st, log = store
        await st.set("ui.theme", "light", USER)
        await st.set("llm.kimi.api_key", "sk-yyy", USER)
        events = [e for _, e in log.read_after(types=[DomainEvent.SETTINGS_CHANGED])]
        assert len(events) == 2
        assert events[0].payload["value"] == "light"  # non-secret carries the value
        assert "value" not in events[1].payload  # secret omits the value
        assert events[1].payload["secret"] is True
        assert events[0].actor == USER


class TestUserOnly:
    """user_only write protection: writable by the user only, but the value
    is still echoed back (unlike secret)."""

    async def test_agent_write_forbidden_value_unchanged(self, store) -> None:
        st, _ = store
        with pytest.raises(ServiceError) as exc:
            await st.set("agent.network.mode", "all", AGENT)
        assert exc.value.body.code == "SETTINGS.FORBIDDEN"
        assert exc.value.http_status == 403
        assert st.get("agent.network.mode") == "whitelist"  # value unchanged

    async def test_system_write_forbidden_too(self, store) -> None:
        """The gate checks actor.kind: internal calls without a user (SYSTEM)
        are equally barred from writing sensitive settings."""
        st, _ = store
        with pytest.raises(ServiceError) as exc:
            await st.set("agent.network.mode", "all", SYSTEM)
        assert exc.value.body.code == "SETTINGS.FORBIDDEN"

    async def test_user_write_ok_and_schema_keeps_value(self, store) -> None:
        st, _ = store
        await st.set("agent.network.mode", "all", USER)
        assert st.get("agent.network.mode") == "all"
        schema = {item["key"]: item for item in st.list_schema()}
        item = schema["agent.network.mode"]
        assert item["value"] == "all"  # user_only does not hide the value (settings page shows it)
        assert item["secret"] is False

    async def test_change_event_carries_value(self, store) -> None:
        st, log = store
        await st.set("agent.network.mode", "all", USER)
        events = [e for _, e in log.read_after(types=[DomainEvent.SETTINGS_CHANGED])]
        assert events[-1].payload["value"] == "all"  # unlike secret, the event carries the value
