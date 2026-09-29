"""resolve_model_name: the shared settings fallback chain that single-sources
"which model name does the wire actually serve" for every consumer (context
windows, output caps, the system head's environment line).

The chain order is the contract: client ``model`` attribute first, then the
standalone-run setting (agent.llm.model), then the composer's chat model
(llm.default_model). A reorder silently changes which model those consumers
account for, so the order is pinned here directly, not only through the
output-cap wrapper.
"""

from agent.runtime.tokens import resolve_model_name
from platform_contracts import ErrorSuffix, ServiceError

_BOTH_KEYS = {"agent.llm.model": "standalone-model", "llm.default_model": "chat-model"}


class _StoreSettings:
    """SettingsStore semantics: unknown keys raise ServiceError (its real
    signal for unregistered keys), known keys return the stored value."""

    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, key: str) -> str:
        try:
            return self._values[key]
        except KeyError as exc:
            raise ServiceError(
                "settings", ErrorSuffix.NOT_FOUND, f"unregistered settings key: {key}"
            ) from exc


class _KeyErrorSettings:
    """Tolerant test double per the contract: raises KeyError like a plain
    dict-shaped settings stand-in would."""

    def get(self, key: str) -> str:
        raise KeyError(key)


class _Client:
    def __init__(self, model: str | None) -> None:
        self.model = model


def test_client_attr_wins_over_both_settings() -> None:
    assert resolve_model_name(_Client("wire-model"), _StoreSettings(_BOTH_KEYS)) == "wire-model"


def test_unset_client_attr_falls_to_the_standalone_setting() -> None:
    assert resolve_model_name(_Client(""), _StoreSettings(_BOTH_KEYS)) == "standalone-model"


def test_missing_client_attr_falls_to_the_standalone_setting() -> None:
    assert resolve_model_name(object(), _StoreSettings(_BOTH_KEYS)) == "standalone-model"


def test_none_client_attr_counts_as_unset() -> None:
    assert resolve_model_name(_Client(None), _StoreSettings(_BOTH_KEYS)) == "standalone-model"


def test_standalone_setting_missing_falls_to_the_composer_default() -> None:
    # agent-only builds do not register the llm-domain keys: the read of
    # agent.llm.model raises ServiceError and the chain moves on
    assert (
        resolve_model_name(_Client(""), _StoreSettings({"llm.default_model": "chat-model"}))
        == "chat-model"
    )


def test_chain_order_of_the_settings_hops_is_standalone_first() -> None:
    # both hops present with an unset client attr: the standalone key wins,
    # so a reorder of the two settings hops would flip the effective name
    assert resolve_model_name(_Client(""), _StoreSettings(_BOTH_KEYS)) == "standalone-model"


def test_all_sources_empty_yield_an_empty_name() -> None:
    assert resolve_model_name(_Client(""), _StoreSettings({})) == ""


def test_key_error_double_degrades_to_empty_instead_of_raising() -> None:
    assert resolve_model_name(_Client(""), _KeyErrorSettings()) == ""
