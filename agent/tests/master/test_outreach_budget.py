"""Outreach anti-bombing budget: caps, cooldown, quiet hours, global switch."""

from __future__ import annotations

import time

from agent.master.outreach_budget import OutreachBudget


class _S:
    def __init__(self, values: dict | None = None) -> None:
        self.values = values or {}

    def get(self, key: str):
        return self.values.get(key)


NOW = time.time()


class TestBudget:
    def test_global_switch_off(self) -> None:
        b = OutreachBudget(_S({"agent.outreach.enabled": False}))
        d = b.allow(session="s", now_ts=NOW)
        assert d.allow is False and "disabled" in d.reason

    def test_daily_and_session_caps(self) -> None:
        b = OutreachBudget(
            _S(
                {
                    "agent.outreach.daily_max": 2,
                    "agent.outreach.session_max": 1,
                    "agent.outreach.cooldown_minutes": 0,
                    "agent.outreach.quiet_hours": "",
                }
            )
        )
        for i in range(2):
            assert b.allow(session=f"s{i}", now_ts=NOW).allow
            b.record(session=f"s{i}", now_ts=NOW)
        assert b.allow(session="s2", now_ts=NOW).allow is False  # daily cap
        assert b.allow(session="s2", now_ts=NOW + 90000).allow  # next day

    def test_cooldown_and_quiet_hours(self) -> None:
        b = OutreachBudget(
            _S(
                {
                    "agent.outreach.cooldown_minutes": 60,
                    "agent.outreach.quiet_hours": "",
                    "agent.outreach.session_max": 0,
                    "agent.outreach.daily_max": 0,
                }
            )
        )
        b.record(session="s", now_ts=NOW)
        d = b.allow(session="t", now_ts=NOW + 60)
        assert d.allow is False and "cooldown" in d.reason
        assert b.allow(session="s", now_ts=NOW + 3700).allow

    def test_quiet_hours_span_midnight(self) -> None:
        b = OutreachBudget(
            _S(
                {
                    "agent.outreach.quiet_hours": "23:00-08:00",
                    "agent.outreach.daily_max": 0,
                    "agent.outreach.session_max": 0,
                    "agent.outreach.cooldown_minutes": 0,
                }
            )
        )
        # 23:30 local today -> inside quiet hours regardless of date
        lt = time.localtime(NOW)
        quiet_ts = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 23, 30, 0, 0, 0, -1))
        assert b.allow(session="s", now_ts=quiet_ts).allow is False
        noon = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 12, 0, 0, 0, 0, -1))
        assert b.allow(session="s", now_ts=noon).allow

    def test_fallback_cooldown_is_minutes_not_seconds(self) -> None:
        # Settings read failure falls back to the declared 120 *minutes*
        # (7200s), not 120s — a 60x weaker gate would defeat the anti-bombing
        # default exactly when settings are broken. Pinned to local noon so
        # the default quiet hours (23:00-08:00) never gate the test.
        lt = time.localtime(NOW)
        noon = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 12, 0, 0, 0, 0, -1))
        b = OutreachBudget(_S({}))
        b.record(session="s", now_ts=noon)
        assert b.allow(session="t", now_ts=noon + 7000).allow is False
        assert b.allow(session="t", now_ts=noon + 7300).allow

    def test_bounded_history(self) -> None:
        b = OutreachBudget(
            _S(
                {
                    "agent.outreach.cooldown_minutes": 0,
                    "agent.outreach.daily_max": 0,
                    "agent.outreach.session_max": 0,
                    "agent.outreach.quiet_hours": "",
                }
            )
        )
        for i in range(600):
            b.record(session=f"s{i}", now_ts=NOW)
        assert b.allow(session="last", now_ts=NOW).allow  # history stays bounded, caps honored
