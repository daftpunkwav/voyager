"""Settings write-permission parity: the agent changes settings with the same
rights as the user via the bridge; secret settings are user-writable only.

- The agent calls settings__set_setting on an ordinary item -> succeeds, and the
  settings.changed event carries the agent as actor;
- The agent writes a secret item -> SETTINGS.FORBIDDEN;
- The user writes a secret item -> succeeds, and the schema output only has
  has_value, never value/default.
"""

from agent.llm import ToolCall
from fastapi.testclient import TestClient
from host.assemble import build
from platform_settings import SettingDef, SettingType

_SECRET_KEY = "test.secret_token"


def _backend(tmp_path):
    app = build(tmp_path / "data", tmp_path / "ws")
    # Test-only secret setting (registered dynamically; enters no service defs
    # and does not pollute the production schema)
    app.state.backend.settings_store.register(
        [
            SettingDef(
                key=_SECRET_KEY,
                module="test",
                type=SettingType.STR,
                default="",
                secret=True,
                description="test secret item",
            ),
        ]
    )
    return app


class TestAgentParity:
    async def test_agent_sets_theme_event_carries_agent_actor(self, tmp_path) -> None:
        app = _backend(tmp_path)
        backend = app.state.backend
        belt = backend.agent.spawner._toolbelt
        with TestClient(app):
            out = await belt.call(
                ToolCall(
                    id="t1",
                    name="settings__set_setting",
                    arguments={"key": "appearance.theme", "value": "light"},
                )
            )
            assert "工具失败" not in out and "已拒绝" not in out
            events = [e for _, e in backend.log.read_after(types=["settings.changed"])]
            assert events, "settings.changed not published"
            last = events[-1]
            assert last.actor.kind.value == "agent"  # agent write, traceable via the event
            assert last.payload["key"] == "appearance.theme"
            assert last.payload["value"] == "light"
            assert backend.settings_store.get("appearance.theme") == "light"

    async def test_agent_cannot_write_secret(self, tmp_path) -> None:
        app = _backend(tmp_path)
        belt = app.state.backend.agent.spawner._toolbelt
        with TestClient(app):
            out = await belt.call(
                ToolCall(
                    id="t1",
                    name="settings__set_setting",
                    arguments={"key": _SECRET_KEY, "value": "sk-agent"},
                )
            )
            # Framework-level guard: secrets are user-only, and the agent is
            # rejected through the same capability entry point (the toolbelt
            # turns ServiceError into a text result; the code is conveyed by the
            # message semantics)
            assert "writable by the user only" in out
            assert app.state.backend.settings_store.get(_SECRET_KEY) == ""


class TestUserSecret:
    def test_user_writes_secret_schema_hides_value(self, tmp_path) -> None:
        app = _backend(tmp_path)
        with TestClient(app) as client:
            resp = client.post(
                "/api/settings/capabilities/set_setting",
                json={"key": _SECRET_KEY, "value": "sk-user"},
            )
            item = resp.json()["result"]
            assert item["has_value"] is True
            assert "value" not in item and "default" not in item  # values never leave the schema

            items = client.post(
                "/api/settings/capabilities/get_settings", json={"module": "test"}
            ).json()["result"]
            assert items[0]["key"] == _SECRET_KEY
            assert items[0]["has_value"] is True
            assert "value" not in items[0]
