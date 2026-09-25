"""Job notifier: quiet preference posts a notice; wakeup starts a turn until
the wake budget is exhausted, then degrades to a quiet notice."""

from __future__ import annotations

from types import SimpleNamespace

from agent.orchestrator.job_notify import JobNotifier
from agent.runtime.wake_budget import WakeBudget


class _FakeMaster:
    def __init__(self) -> None:
        self.replies: list[tuple[str, str]] = []
        self.notices: list[tuple[str, str]] = []
        self.sessions = SimpleNamespace(active_id=lambda: "default-session")

    async def reply(self, text: str, *, trace_id: str = "", session: str = "") -> None:
        self.replies.append((text, session))

    async def handle_notice(self, session: str, text: str) -> None:
        self.notices.append((session, text))


def _job(kind: str = "report", session: str = "s1"):
    return SimpleNamespace(id="j-1", kind=kind, payload={"session": session})


async def test_quiet_preference_posts_notice_without_turn() -> None:
    master = _FakeMaster()
    notifier = JobNotifier(master, WakeBudget())
    await notifier(_job(), ok=True, error="", pref="quiet")
    assert master.replies and master.notices == []


async def test_wakeup_starts_turn_and_consumes_budget() -> None:
    master = _FakeMaster()
    budget = WakeBudget()
    notifier = JobNotifier(master, budget)
    await notifier(_job(), ok=True, error="", pref="wakeup")
    await notifier(_job(), ok=True, error="", pref="wakeup")
    await notifier(_job(), ok=True, error="", pref="wakeup")
    assert len(master.notices) == 3 and master.replies == []
    # Fourth consecutive wakeup degrades to a quiet notice
    await notifier(_job(), ok=True, error="", pref="wakeup")
    assert len(master.notices) == 3
    assert master.replies and "[后台任务]" in master.replies[0][0]


async def test_failed_job_carries_error_head() -> None:
    master = _FakeMaster()
    notifier = JobNotifier(master, WakeBudget())
    await notifier(_job(), ok=False, error="ValueError: boom", pref="quiet")
    text = master.replies[0][0]
    assert "失败" in text and "ValueError" in text


async def test_missing_session_falls_back_to_active() -> None:
    master = _FakeMaster()
    notifier = JobNotifier(master, WakeBudget())
    job = _job(session="")
    await notifier(job, ok=True, error="", pref="quiet")
    assert master.replies[0][1] == "default-session"
