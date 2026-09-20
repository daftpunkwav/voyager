"""Terminal REPL: talk to the full agent from a console, without
the web UI or any domain service.

Responsibilities:
- ReplSession: the asyncio core - subscribes ``agent.*`` events on the bus,
  renders deltas/steps/messages through an output sink, and routes each
  input line either to a pending ask_user question (answered via the same
  ``AskUser.answer`` channel the frontend uses) or to
  ``master.handle_user_message`` (the same entry the Chat page drives, so
  arbitration, dispatch, tools, and todos all behave identically)
- Slash commands (/help /todo /memory /sessions /compact /replay /quit): local
  reads only, no LLM
- _standalone_llm(): pick the LLM for standalone runs - an OpenAI-compatible
  HttpLLM when agent.llm.base_url + agent.llm.model are configured, a
  self-explanatory FakeLLM otherwise
- main(): register agent settings, pick the standalone LLM, assemble via
  build_agent, and run the stdio shell

Run from the repository root: ``python -m agent.repl``.
"""

from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform_contracts import DomainEvent, Event
from platform_eventbus import Subscription
from platform_settings import SettingsStore

from agent.llm import FakeLLM, LLMClient
from agent.llm_http import HttpLLM, HttpLlmConfig
from agent.main import AgentApp, build_agent
from agent.settings import DEFS as AGENT_SETTING_DEFS

_HELP = """\
Commands:
  /help    show this help
  /todo    show the current task plan (todo list)
  /memory  show a memory snapshot (profile / episodic / semantic)
  /sessions        list chat sessions
  /session [id]    switch the active chat session (bare: list)
  /compact [id]    compact a session's context (default: active)
  /replay [run_id] show recent runs; with an id, replay its step trail read-only
  /quit    leave the REPL (alias: /exit)
Everything else is sent to the agent as a chat message.
When the agent asks a question, your next line is delivered as the answer.
"""

_CONFIRM_YES = {"y", "yes", "ok", "是", "确认", "好", "行"}
_PROMPT = "you> "


@dataclass(frozen=True)
class _PendingAsk:
    """One open ask_user question awaiting the next input line."""

    question_id: str
    kind: str
    options: tuple[str, ...]


class ReplSession:
    """Asyncio core of the REPL: event consumption + input routing.

    Rendering goes through a synchronous sink (``out``) so the component is
    testable without a terminal; the stdio shell passes ``print``-backed
    writers, tests collect strings.
    """

    def __init__(self, app: AgentApp, *, out: Callable[[str], None]) -> None:
        self._app = app
        self._out = out
        self._pending: _PendingAsk | None = None
        self._sub: Subscription | None = None
        self._consumer: asyncio.Task | None = None

    def start(self) -> None:
        self._sub = self._app.bus.subscribe("agent.*")
        self._consumer = asyncio.create_task(self._consume())

    async def close(self) -> None:
        if self._consumer is not None:
            self._consumer.cancel()
            try:
                await self._consumer
            except asyncio.CancelledError:
                pass
            self._consumer = None
        if self._sub is not None:
            self._app.bus.unsubscribe(self._sub)
            self._sub = None

    async def _consume(self) -> None:
        """Drain the subscription forever; a timeout tick keeps the task
        responsive to cancellation."""
        assert self._sub is not None
        while True:
            try:
                event = await self._sub.get(timeout=0.5)
            except TimeoutError:
                continue
            self.render(event)

    def render(self, event: Event) -> None:
        """Render one agent event through the sink (public for tests)."""
        p = event.payload or {}
        t = event.type
        if t == DomainEvent.AGENT_DELTA:
            self._out(str(p.get("text") or ""))
        elif t == DomainEvent.AGENT_STEP:
            self._out(f"\n  · [{p.get('kind')}] {p.get('name')}: {p.get('summary')}")
        elif t == DomainEvent.AGENT_MESSAGE:
            self._out(f"\nagent> {p.get('content')}\n")
        elif t == DomainEvent.AGENT_ASK:
            self._open_ask(p)
        elif t == DomainEvent.AGENT_POLICY_NOTIFY:
            self._out(f"\n[notify] {p.get('message')}\n")

    def _open_ask(self, payload: dict[str, Any]) -> None:
        """Register an open question; the next input line becomes the answer."""
        kind = str(payload.get("kind") or "text")
        options = tuple(str(o) for o in (payload.get("options") or ()))
        self._pending = _PendingAsk(
            question_id=str(payload.get("question_id") or ""),
            kind=kind,
            options=options,
        )
        hint = {
            "confirm": " (y/n)",
            "choice": f" (pick 1-{len(options)})" if options else "",
        }.get(kind, "")
        self._out(f"\nagent asks> {payload.get('prompt')}{hint}\n")

    async def submit(self, line: str) -> bool:
        """Route one input line. Returns False when the REPL should exit.

        Priority: slash command > pending ask answer > chat message.
        """
        text = line.strip()
        if not text:
            return True
        if text.startswith("/"):
            return await self._command(text)
        if self._pending is not None:
            self._answer_pending(text)
            return True
        await self._app.master.handle_user_message(text)
        return True

    def _answer_pending(self, line: str) -> None:
        assert self._pending is not None
        pending, self._pending = self._pending, None
        value = _coerce_answer(pending.kind, pending.options, line)
        if not self._app.asker.answer(pending.question_id, value):
            self._out("[the question already expired; sent nothing]\n")

    async def _command(self, text: str) -> bool:
        parts = text[1:].split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""
        if cmd in ("quit", "exit", "q"):
            return False
        if cmd == "help":
            self._out(_HELP)
        elif cmd == "todo":
            self._out(f"{_fmt(await self._call('todowrite', {'action': 'query'}))}\n")
        elif cmd == "memory":
            self._out(f"{_fmt(await self._call('get_memory'))}\n")
        elif cmd == "sessions":
            self._out(f"{_fmt(await self._call('session', {'action': 'list'}))}\n")
        elif cmd == "session":
            # /session <id>: switch the active session; bare /session: list
            if arg:
                self._out(
                    f"{_fmt(await self._call('session', {'action': 'set_active', 'session_id': arg}))}\n"
                )
            else:
                self._out(f"{_fmt(await self._call('session', {'action': 'list'}))}\n")
        elif cmd == "replay":
            self._replay(arg)
        elif cmd == "compact":
            self._out(f"{_fmt(await self._call('compact_context', {'session_id': arg}))}\n")
        else:
            self._out(f"[unknown command /{cmd}; try /help]\n")
        return True

    def _replay(self, run_id: str) -> None:
        """Read-only run replay from the trajectory projection: bare command
        lists recent runs; with an id, renders the step trail (never re-executes)."""
        store = self._app.trajectory
        if not run_id:
            runs = store.list_runs(limit=10)
            if not runs:
                self._out("(no recorded runs yet)\n")
                return
            lines = [
                f"{r['run_id'][:12]}  {r['status']:<9} steps={r['steps']:<3} "
                f"{r['subagent'] or '-'}  {r['session'] or '-'}"
                for r in runs
            ]
            self._out(
                "recent runs (id prefix, status, steps, subagent, session):\n"
                + "\n".join(lines)
                + "\n"
            )
            return
        run = next((r for r in store.list_runs(limit=500) if r["run_id"].startswith(run_id)), None)
        if run is None:
            self._out(f"[no run matching {run_id}]\n")
            return
        full = run["run_id"]
        head = (
            f"run {full} ({run['status']}, {run['steps']} steps, "
            f"in={run['input_tokens']} out={run['output_tokens']} tokens)"
        )
        lines = [head]
        for step in store.run_steps(full):
            payload = step["payload"]
            lines.append(
                f"  · [{payload.get('kind')}] {payload.get('name')}: {payload.get('summary')}"
            )
        self._out("\n".join(lines) + "\n")

    async def _call(self, name: str, args: dict | None = None) -> Any:
        """Invoke an agent capability from a slash command (command path only;
        the conversation path never goes through here). Awaits async handlers —
        compact_context et al. are coroutines and would otherwise render as an
        unawaited coroutine object instead of running."""
        cap = self._app.registry.get(name)
        result = cap.handler(**(args or {}))
        if inspect.isawaitable(result):
            result = await result
        return result


def _coerce_answer(kind: str, options: tuple[str, ...], line: str) -> Any:
    """Turn a raw terminal line into the answer value the tool expects."""
    if kind == "confirm":
        return line.strip().lower() in _CONFIRM_YES
    if kind == "choice" and options:
        if line.isdigit() and 1 <= int(line) <= len(options):
            return options[int(line) - 1]
        if line in options:
            return line
        return options[0]
    if kind == "multi_choice":
        # Separator-split items; each maps by 1-based index or exact text,
        # unknown tokens pass through (free text is always a legal answer)
        tokens = [t.strip() for t in re.split(r"[、，,;/]", line) if t.strip()]
        picked = []
        for token in tokens:
            if token.isdigit() and 1 <= int(token) <= len(options):
                picked.append(options[int(token) - 1])
            else:
                picked.append(token)
        return picked
    if kind == "rating":
        # Five-star review: an integer 1-5; anything unparsable (text, nan) or
        # unbounded ("inf" raises OverflowError on int()) passes through as text
        try:
            return max(1, min(int(float(line)), 5))
        except (ValueError, OverflowError):
            return line
    if kind == "slider":
        try:
            return float(line)
        except ValueError:
            return 0.0
    return line


def _fmt(result: Any) -> str:
    """Render a capability result readably (dict/list -> line-per-item)."""
    if isinstance(result, dict):
        if "items" in result and isinstance(result["items"], list):
            items = result["items"]
            if not items:
                return "(todo list is empty)"
            return "\n".join(
                f"[{'x' if i.get('done') else ' '}] {i.get('content', '')}" for i in items
            )
        return "\n".join(f"{k}: {v}" for k, v in result.items())
    return str(result)


def _standalone_llm(settings: Any) -> LLMClient:
    """LLM for standalone runs: a real OpenAI-compatible endpoint when
    configured, otherwise a FakeLLM whose replies explain how to configure
    one (never a silent stub)."""
    base_url = str(settings.get("agent.llm.base_url") or "").strip()
    model = str(settings.get("agent.llm.model") or "").strip()
    if base_url and model:
        return HttpLLM(
            HttpLlmConfig(
                base_url=base_url,
                api_key=str(settings.get("agent.llm.api_key") or ""),
                model=model,
                timeout_s=float(settings.get("agent.llm.timeout_s") or 120),
            )
        )
    return FakeLLM(
        default=(
            "[FakeLLM] 未配置真实模型。请设置 agent.llm.base_url 与 agent.llm.model"
            "(任意 OpenAI 兼容端点)后重启 REPL。"
        )
    )


async def _run_stdio(app: AgentApp) -> None:
    """Stdio shell: read lines on a worker thread, route via ReplSession."""
    session = ReplSession(app, out=lambda s: print(s, end="", flush=True))
    session.start()
    print("agent REPL ready - /help for commands, /quit to leave")
    loop = asyncio.get_running_loop()
    try:
        while True:
            line = await loop.run_in_executor(None, input, _PROMPT)
            if not await session.submit(line):
                break
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        await session.close()
        print("bye")


def main() -> None:
    """Entry point: standalone data dir, LLM chosen from agent.llm.* settings,
    stdio shell. The settings keys must be registered before the LLM read
    (register_fresh is idempotent), and the store is owned here because it is
    shared into the assembly."""
    data_dir = Path("data/runtime")
    settings = SettingsStore(data_dir / "settings.db")
    settings.register_fresh(AGENT_SETTING_DEFS)
    llm = _standalone_llm(settings)
    app = build_agent(data_dir=data_dir, settings_store=settings, llm=llm)
    try:
        asyncio.run(_run_stdio(app))
    finally:
        app.close()
        settings.close()
        if isinstance(llm, HttpLLM):
            asyncio.run(llm.aclose())  # fresh loop: the stdio loop is already gone


if __name__ == "__main__":
    main()


__all__ = ["ReplSession", "_standalone_llm", "main"]
