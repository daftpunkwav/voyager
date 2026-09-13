"""Tests for the model price table and the meter cost view: normalization,
fuzzy lookup, override precedence, cost math (cached share), and the
explicit unknown-model bucket (never priced at zero)."""

from agent.runtime import pricing
from agent.runtime.meter import Meter, MeterRecord
from agent.runtime.meter_store import MeterStore


class TestNormalize:
    def test_known_provider_prefixes_strip(self) -> None:
        assert pricing.normalize_model("openrouter/deepseek/DeepSeek-Chat") == "deepseek-chat"
        assert pricing.normalize_model("anthropic/claude-sonnet-4-5") == "claude-sonnet-4-5"
        assert pricing.normalize_model("DeepSeek/deepseek-chat") == "deepseek-chat"

    def test_unknown_prefix_collapses_to_last_segment(self) -> None:
        assert pricing.normalize_model("some-gateway/gpt-4o") == "gpt-4o"

    def test_plain_name_unchanged(self) -> None:
        assert pricing.normalize_model("gpt-4o") == "gpt-4o"
        assert pricing.normalize_model("") == ""


class TestLookup:
    def test_exact_and_substring(self) -> None:
        assert pricing.lookup("deepseek-chat") is not None
        assert pricing.lookup("openrouter/deepseek/deepseek-chat") is not None
        assert pricing.lookup("deepseek-chat-v3.2") is not None  # substring family match

    def test_unknown_model_is_none(self) -> None:
        assert pricing.lookup("totally-made-up-model") is None

    def test_override_wins(self) -> None:
        overrides = {"gpt-4o": {"input": 9.0, "output": 9.0}}
        price = pricing.lookup("gpt-4o", overrides=overrides)
        assert price is not None and price.input == 9.0 and price.output == 9.0

    def test_dirty_override_falls_back_to_table(self) -> None:
        price = pricing.lookup("gpt-4o", overrides={"gpt-4o": {"input": "cheap"}})
        assert price is not None and price.input == 2.50


class TestCostOf:
    def test_plain_math(self) -> None:
        cost = pricing.cost_of("deepseek-chat", input_tokens=1_000_000, output_tokens=1_000_000)
        assert cost is not None
        assert abs(cost - (0.27 + 1.10)) < 1e-9

    def test_cached_share_billed_at_cache_rate(self) -> None:
        cost = pricing.cost_of(
            "deepseek-chat",
            input_tokens=1_000_000,
            output_tokens=0,
            cached_tokens=400_000,
        )
        assert cost is not None
        assert abs(cost - (0.6 * 0.27 + 0.4 * 0.07)) < 1e-9

    def test_cached_above_input_is_clamped(self) -> None:
        cost = pricing.cost_of(
            "deepseek-chat", input_tokens=100, output_tokens=0, cached_tokens=9_999
        )
        assert cost is not None
        assert abs(cost - 100 * 0.07 / 1_000_000) < 1e-12

    def test_unknown_model_returns_none(self) -> None:
        assert pricing.cost_of("nope", input_tokens=1, output_tokens=1) is None


class TestMeterCostView:
    def test_store_path_accumulates_and_prices(self, tmp_path) -> None:
        meter = Meter(store=MeterStore(tmp_path / "meter.db"))
        meter.record(MeterRecord(kind="llm", name="deepseek-chat", ms=1.0, input_tokens=1_000_000))
        meter.record(
            MeterRecord(
                kind="llm",
                name="deepseek-chat",
                ms=1.0,
                input_tokens=1_000_000,
                output_tokens=500_000,
                cached_tokens=400_000,
            )
        )
        view = meter.cost_today()
        expected = 0.27 + (0.6 * 0.27 + 0.4 * 0.07 + 0.5 * 1.10)
        assert abs(view["cost_usd"] - expected) < 1e-6
        assert view["unknown"] == []
        meter.close()

    def test_unknown_models_surfaced_not_zeroed(self, tmp_path) -> None:
        meter = Meter(store=MeterStore(tmp_path / "meter.db"))
        meter.record(MeterRecord(kind="llm", name="mystery-llm", ms=1.0, input_tokens=5_000_000))
        view = meter.cost_today()
        assert view["unknown"] == ["mystery-llm"]
        assert view["cost_usd"] == 0.0
        meter.close()

    def test_in_memory_fallback(self) -> None:
        meter = Meter()
        meter.record(MeterRecord(kind="llm", name="gpt-4o", ms=1.0, input_tokens=2_000_000))
        view = meter.cost_today()
        assert abs(view["cost_usd"] - 2 * 2.50) < 1e-6

    def test_overrides_fn_applies(self) -> None:
        meter = Meter(pricing_overrides_fn=lambda: {"gpt-4o": {"input": 1.0, "output": 1.0}})
        meter.record(MeterRecord(kind="llm", name="gpt-4o", ms=1.0, input_tokens=1_000_000))
        view = meter.cost_today()
        assert abs(view["cost_usd"] - 1.0) < 1e-9

    def test_dirty_overrides_fn_falls_back(self) -> None:
        def _boom():
            raise RuntimeError("dirty settings")

        meter = Meter(pricing_overrides_fn=_boom)
        meter.record(MeterRecord(kind="llm", name="gpt-4o", ms=1.0, input_tokens=1_000_000))
        view = meter.cost_today()
        assert abs(view["cost_usd"] - 2.50) < 1e-9
