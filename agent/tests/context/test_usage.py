"""Tests for context-window accounting: per-model limit resolution,
usage anchoring on provider-reported tokens, and the status line the model
reads each turn.
"""

from agent.context.usage import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_WINDOW_TOKENS,
    ContextWindow,
    UsageTracker,
    over_threshold,
    render_status_line,
    resolve_window,
    usage_status,
)


class _FakeSettings:
    """Minimal SettingsReader over a dict (same duck type as SettingsStore)."""

    def __init__(self, values: dict | None = None) -> None:
        self._values = dict(values or {})

    def get(self, key: str, default=None):
        return self._values.get(key, default)


class TestResolveWindow:
    def test_defaults_when_nothing_set(self) -> None:
        resolved = resolve_window(_FakeSettings())
        assert resolved.window_tokens == DEFAULT_WINDOW_TOKENS
        assert resolved.max_output_tokens == DEFAULT_MAX_OUTPUT_TOKENS
        assert resolved.usable == DEFAULT_WINDOW_TOKENS - DEFAULT_MAX_OUTPUT_TOKENS

    def test_global_keys_override_defaults(self) -> None:
        settings = _FakeSettings(
            {
                "agent.context.window_tokens": 128_000,
                "agent.context.max_output_tokens": 8_192,
            }
        )
        resolved = resolve_window(settings)
        assert resolved.window_tokens == 128_000
        assert resolved.max_output_tokens == 8_192
        assert resolved.usable == 128_000 - 8_192

    def test_model_profile_wins_over_globals(self) -> None:
        settings = _FakeSettings(
            {
                "agent.context.window_tokens": 200_000,
                "agent.context.max_output_tokens": 64_000,
                "agent.context.model_profiles": {
                    "deepseek-chat": {"window_tokens": 128_000, "max_output_tokens": 8_192},
                },
            }
        )
        resolved = resolve_window(settings, model_name="deepseek-chat")
        assert resolved.window_tokens == 128_000
        assert resolved.max_output_tokens == 8_192
        # A different model keeps the globals
        other = resolve_window(settings, model_name="glm-5.3")
        assert other.window_tokens == 200_000
        # No model name keeps the globals
        none = resolve_window(settings)
        assert none.window_tokens == 200_000

    def test_malformed_values_fall_back(self) -> None:
        settings = _FakeSettings(
            {
                "agent.context.window_tokens": "not-a-number",
                "agent.context.max_output_tokens": -5,
                "agent.context.model_profiles": {
                    "m1": "junk",  # non-dict entry -> ignored
                },
            }
        )
        resolved = resolve_window(settings, model_name="m1")
        assert resolved.window_tokens == DEFAULT_WINDOW_TOKENS
        assert resolved.max_output_tokens == DEFAULT_MAX_OUTPUT_TOKENS

    def test_profile_partial_fields_keep_global_rest(self) -> None:
        settings = _FakeSettings(
            {
                "agent.context.window_tokens": 200_000,
                "agent.context.max_output_tokens": 64_000,
                "agent.context.model_profiles": {"m1": {"window_tokens": 32_000}},
            }
        )
        resolved = resolve_window(settings, model_name="m1")
        assert resolved.window_tokens == 32_000
        assert resolved.max_output_tokens == 64_000

    def test_usable_never_zero(self) -> None:
        degenerate = ContextWindow(window_tokens=1_000, max_output_tokens=5_000)
        assert degenerate.usable == 1


class TestUsageStatus:
    def test_anchors_on_reported_when_larger(self) -> None:
        tracker = UsageTracker()
        tracker.record(90_000)
        messages = [{"role": "user", "content": "hi"}]  # tiny estimate
        status = usage_status(ContextWindow(200_000, 64_000), messages, tracker, auto_compact_at=75)
        assert status["reported_tokens"] == 90_000
        assert status["used_tokens"] == 90_000

    def test_estimate_wins_when_reported_missing_or_stale(self) -> None:
        tracker = UsageTracker()
        messages = [
            {"role": "user", "content": "hello world " * 100},
            {"role": "assistant", "content": "reply " * 200},
        ]
        status = usage_status(ContextWindow(200_000, 64_000), messages, tracker, auto_compact_at=75)
        assert status["used_tokens"] == status["estimate_tokens"]
        tracker.record(1)  # negligible report must not lower the anchor
        status2 = usage_status(
            ContextWindow(200_000, 64_000), messages, tracker, auto_compact_at=75
        )
        assert status2["used_tokens"] == status2["estimate_tokens"]

    def test_over_threshold_uses_percent(self) -> None:
        window = ContextWindow(window_tokens=100_000, max_output_tokens=50_000)
        tracker = UsageTracker()
        tracker.record(37_500)  # exactly 75% of usable (50k)
        status = usage_status(window, [], tracker, auto_compact_at=75)
        assert status["used_pct"] == 75.0
        assert over_threshold(status) is True
        tracker2 = UsageTracker()
        status2 = usage_status(window, [], tracker2, auto_compact_at=75)
        assert over_threshold(status2) is False

    def test_reset_drops_stale_anchor_after_compaction(self) -> None:
        tracker = UsageTracker()
        tracker.record(90_000)
        tracker.reset()
        assert tracker.last_reported == 0
        messages = [{"role": "user", "content": "hi"}]
        status = usage_status(ContextWindow(200_000, 64_000), messages, tracker, auto_compact_at=75)
        assert status["used_tokens"] == status["estimate_tokens"]


class TestStatusLine:
    def test_line_carries_window_and_threshold(self) -> None:
        window = ContextWindow(200_000, 64_000)
        status = usage_status(window, [], UsageTracker(), auto_compact_at=75)
        line = render_status_line(status)
        assert "200000" in line
        assert "75%" in line
        assert "context(action=compact)" in line

    def test_line_appends_session_when_present(self) -> None:
        status = usage_status(
            ContextWindow(200_000, 64_000), [], UsageTracker(), auto_compact_at=75
        )
        plain = render_status_line(status)
        with_session = render_status_line(status, session="ab12cd34")
        assert "ab12cd34" not in plain
        assert "ab12cd34" in with_session


class TestCacheStableStatusLine:
    """The status line rides inside the system message (the token-prefix head):
    it must stay byte-identical across most turns or the provider prompt cache
    is invalidated every round."""

    def _line(self, used_pct: float) -> str:
        window = ContextWindow(200_000, 64_000)
        tracker = UsageTracker()
        tracker.record(int(used_pct / 100 * window.usable))
        return render_status_line(usage_status(window, [], tracker, auto_compact_at=75))

    def test_same_bucket_renders_identical_line(self) -> None:
        # 71.2% and 73.9% share the 70-75 bucket: the line must not move
        assert self._line(71.2) == self._line(73.9)

    def test_crossing_bucket_changes_the_line(self) -> None:
        assert self._line(74.9) != self._line(75.1)

    def test_exact_token_count_never_leaks_into_the_prefix(self) -> None:
        line = self._line(71.2)
        assert "101080" not in line  # exact used tokens stay out of the system entry

    def test_bucket_floor_is_rendered(self) -> None:
        assert "已用约 70%+" in self._line(71.2)
