"""Tool call execution pipeline: runs one ToolCall through
validation, permission modes, policy, confirmation, hooks, retry, circuit
breaking, and metering.

This module is the invocation implementation behind agent.tools.core.base.Toolbelt.
Types and the roster stay in base.py; this file only owns "how one call is
executed". The input is the constrained view from Toolbelt.invocation_view():
only public fields of the view are used, never Toolbelt private state.
invoke_tool returns the LLM-facing text; invoke_detailed returns the full
ToolResult for tracing and UI layers (same pipeline, same text).

Confirmation is retired: the L2 branch only fires for writes into
user-configured fs write_roots (decision.confirm_scope == "write_roots") —
every other former-L2 outcome (shell commands, workspace deletes, skill
writes) executes directly; the tool permission modes (view.permissions) and
the dimension policies are the remaining gates.
"""

from __future__ import annotations

import asyncio
import difflib
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from agent.llm import ToolCall
from agent.policy import Action, Level
from agent.runtime.meter import MeterRecord
from agent.runtime.recovery import CircuitBreaker, CircuitOpenError, with_retry
from agent.runtime.trace import start_span
from agent.tools.core.model import AgentTool, ToolbeltView
from agent.tools.core.outcome import ToolResult, normalize

#: Long-tool progress outlet: (fraction 0.0-1.0, message) -> None.
ProgressCb = Callable[[float, str], Awaitable[None]]


def _breaker_for(view: ToolbeltView, name: str) -> CircuitBreaker:
    """One circuit breaker per tool name: lazily created; views share the same
    dict, so breaker state survives view rebuilds."""
    cb = view.breakers.get(name)
    if cb is None:
        cb = CircuitBreaker()  # default: open after 3 consecutive failures, 30s
        view.breakers[name] = cb
    return cb


async def _invoke_with_recovery(
    view: ToolbeltView,
    tool: AgentTool,
    call: ToolCall,
    *,
    on_progress: ProgressCb | None = None,
) -> Any:
    """Wraps handler execution with retry + circuit breaking.

    - Read-only / network GET-like tools may retry; write / irreversible tools
      never retry (a retry would double-write or double-delete);
    - The breaker counts failures per **handler execution**: every attempt
      inside with_retry goes through breaker.call individually; 3 consecutive
      handler failures open the circuit (instead of counting once per outer
      belt.call);
    - TimeoutError / asyncio.TimeoutError are not retried by default: MCP/shell
      timeouts multiplied by backoff retries only prolong the wait; a single
      timeout fails immediately and is left to the breaker/text result.
      httpx.TimeoutException likewise: URL-based MCP timeouts (httpx.AsyncClient
      in session.py) behave like stdio MCP — one failure and stop;
    - CircuitOpenError after the breaker opens does not enter the retry loop; it
      propagates (invoke_tool folds it into a "[breaker]" text result);
    - Policy denial / user non-confirmation / pre_tool interception return
      earlier in invoke_tool() and never reach here, so they are neither
      retried nor counted as breaker failures;
    - Backoff comes from Toolbelt constructor args; unit tests inject 0 to
      avoid real sleeps.
    - on_progress is forwarded only to handlers declaring a `progress_cb`
      parameter (long tools: download / scan / bulk IO); other handlers run
      unchanged. Sync handlers never receive it (async outlet cannot run in
      a worker thread).
    """
    breaker = _breaker_for(view, tool.name)
    retries = 0 if (tool.write or tool.irreversible) else view.retries

    def _wants_progress() -> bool:
        try:
            return "progress_cb" in inspect.signature(tool.handler).parameters
        except (TypeError, ValueError):
            return False

    wants_progress = _wants_progress() and on_progress is not None
    is_async = inspect.iscoroutinefunction(tool.handler)

    async def _attempt_once() -> Any:
        # Sync handlers run in a worker thread (same discipline as the
        # capability framework's guards._invoke): blocking IO from fs/sqlite
        # tools directly on the event loop would stall the whole process
        extra: dict[str, Any] = {}
        if wants_progress and is_async:
            # A model-supplied "progress_cb" argument must never win: the
            # outlet is harness-owned, so drop the colliding key instead of
            # raising a duplicate-keyword TypeError.
            args = {k: v for k, v in call.arguments.items() if k != "progress_cb"}
            extra["progress_cb"] = on_progress
        else:
            args = call.arguments
        if is_async:
            run = tool.handler(**args, **extra)
        else:
            run = asyncio.to_thread(tool.handler, **call.arguments)
        if tool.timeout_s is not None:
            # Per-tool cap; TimeoutError is in the no_retry list below, so a
            # timeout fails this call immediately instead of burning backoff.
            # For sync handlers the worker thread cannot be force-killed - it
            # finishes in the background and its result is discarded.
            return await asyncio.wait_for(run, tool.timeout_s)
        return await run

    async def _attempt_with_breaker() -> Any:
        # Every attempt counts through the breaker: success resets, failures
        # accumulate; opens after open_after consecutive failures
        return await breaker.call(_attempt_once)

    return await with_retry(
        _attempt_with_breaker,
        retries=retries,
        backoff=view.retry_backoff,
        no_retry_on=(
            CircuitOpenError,
            TimeoutError,
            asyncio.TimeoutError,
            httpx.TimeoutException,
        ),
    )


async def invoke_tool(
    view: ToolbeltView, call: ToolCall, *, on_progress: ProgressCb | None = None
) -> str:
    """Execute one tool call and return the string result handed to the LLM.

    Order: find tool -> validate arguments -> permission modes -> build policy
    Action -> deny / write_roots confirm / L1 notify -> pre_tool ->
    handler (retry + breaker) -> meter -> post_tool -> stringify.
    """
    return (await invoke_detailed(view, call, on_progress=on_progress)).text


#: JSON-schema type name -> Python check (bool excluded from integer/number:
#: isinstance(True, int) is True, but a boolean is never a valid count).
_TYPE_CHECKS: dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}

#: Python type name -> JSON-schema vocabulary for error messages.
_TYPE_NAMES: dict[str, str] = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
    "NoneType": "null",
}


def validate_arguments(tool: AgentTool, arguments: Any) -> str | None:
    """Check call arguments against the tool schema; None when valid,
    otherwise a model-actionable error message.

    One level only (properties/required): nested objects pass through to the
    handler. Unknown keys are ignored (providers sometimes inject extras).
    An explicit null counts as missing when required, and as absent otherwise
    (handlers treat it with their falsy/default handling).
    """
    if not isinstance(arguments, dict):
        return f"[参数错误] {tool.name}: 参数必须是对象。请以合法对象形式传递参数。"
    schema = tool.schema or {}
    properties = schema.get("properties") or {}
    required = [k for k in (schema.get("required") or []) if isinstance(k, str)]
    missing = [k for k in required if arguments.get(k) is None]
    if missing:
        optional = [k for k in properties if k not in required]
        need = ", ".join(required) or "(无)"
        have = ", ".join(optional) or "(无)"
        return (
            f"[参数错误] {tool.name}: 缺少必需参数 {', '.join(missing)}(需要: {need}; 可选: {have})。"
            "请根据 Schema 补全缺失参数后重试。"
        )
    for key, spec in properties.items():
        if not isinstance(spec, dict):
            continue
        value = arguments.get(key)
        if value is None:
            continue
        want = spec.get("type")
        check = _TYPE_CHECKS.get(want) if isinstance(want, str) else None
        if check is None:
            continue
        if want in ("integer", "number") and isinstance(value, bool):
            matched = False
        else:
            matched = isinstance(value, check)
        if not matched:
            actual = _TYPE_NAMES.get(type(value).__name__, type(value).__name__)
            return (
                f"[参数错误] {tool.name}: 参数 {key} 需要 {want},实际是 {actual}。"
                f"请根据 Schema 修正 {key} 的类型后重试。"
            )
    return None


async def invoke_detailed(
    view: ToolbeltView, call: ToolCall, *, on_progress: ProgressCb | None = None
) -> ToolResult:
    """Execute one tool call and return the full outcome.

    Same pipeline and same LLM-facing text as invoke_tool; ok=False marks
    pipeline rejections and handler failures, and metadata carries
    machine facts (currently: truncated when the result budget spilled).
    on_progress forwards to handlers declaring `progress_cb` (long tools).
    """
    tool = view.tool(call.name)
    if tool is None:
        # Check if the tool belongs to an unactivated domain or MCP
        unactivated_hint = ""
        if "__" in call.name:
            domain_prefix = call.name.split("__")[0]
            unactivated_hint = (
                f";该工具可能属于 '{domain_prefix}' 积木域(尚未激活),"
                f"可使用 activate_tools(domain='{domain_prefix}') 激活"
            )
        # Repair hint: name-similar tools from the current roster, so a typo
        # or a bridged-name guess costs one corrected call instead of a stall
        candidates = difflib.get_close_matches(call.name, view.tools, n=3, cutoff=0.5)
        hint = f";最接近的工具: {', '.join(candidates)}" if candidates else ""
        return ToolResult(
            name=call.name,
            ok=False,
            text=f"[未知工具] {call.name}(可能未授予本 subagent 或名称有误){unactivated_hint}{hint}",
            title=call.name,
        )
    invalid = validate_arguments(tool, call.arguments)
    if invalid is not None:
        # Invalid arguments never reach policy/confirm/hooks/handlers: no
        # side effects, no retries, no breaker counting.
        return ToolResult(name=tool.name, ok=False, text=invalid, title=tool.name)
    # Tool permission modes (agent actor, hot-read): the resolver runs before
    # the dimension policies — mode/deny/allow decide whether the call may be
    # made at all; jail/whitelists then still decide what it may touch.
    if view.permissions is not None:
        denial = view.permissions.check(tool.name, call.arguments)
        if denial is not None:
            return ToolResult(name=tool.name, ok=False, text=denial, title=tool.name)
    # The app-dimension target must be the tool name: bridge tool arguments
    # often carry url/path, and matching those against the `notes__create_note`
    # whitelist would never succeed.
    if tool.dimension == "app":
        target = tool.name
    else:
        target = str(
            call.arguments.get("path")
            or call.arguments.get("url")
            or call.arguments.get("command")
            or tool.name
        )
    decision = view.policy.decide(
        Action(
            dimension=tool.dimension,
            target=target,
            write=tool.write,
            irreversible=tool.irreversible,
        )
    )
    if not decision.allow:
        return ToolResult(
            name=tool.name,
            ok=False,
            text=f"[已拒绝] {decision.reason}",
            title=tool.name,
        )
    if decision.level >= Level.L2_CONFIRM:
        if decision.confirm_scope != "write_roots":
            # Confirm retired: every other former-L2 outcome (shell commands,
            # workspace deletes, skill writes) executes directly; the remaining
            # gates are the permission modes above plus the dimension policies.
            pass
        else:
            # The one kept confirmation: writes into user-configured write_roots
            # ("extra directories are writable, but confirm with me"). Every
            # call asks — there is no approval memory to shortcut it.
            if view.confirm is not None:
                if not await view.confirm(f"允许执行 {tool.name}({target})吗?"):
                    return ToolResult(
                        name=tool.name, ok=False, text="[已取消] 用户未确认", title=tool.name
                    )
            else:
                return ToolResult(
                    name=tool.name,
                    ok=False,
                    text=f"[需确认] {tool.name}({target})需用户确认,当前无可确认通道,已跳过",
                    title=tool.name,
                )
    elif decision.level == Level.L1_NOTIFY and view.notify is not None:
        await view.notify(f"{tool.name}: {target}")
    if view.hooks is not None:
        # pre_tool: any hook returning False blocks; the handler is not executed
        pre = await view.hooks.fire("pre_tool", name=tool.name, arguments=call.arguments)
        if any(r is False for r in pre):
            return ToolResult(
                name=tool.name,
                ok=False,
                text=f"[已拦截] {tool.name}({target})被 pre_tool hook 拦截",
                title=tool.name,
            )
    start = time.perf_counter()
    ok = True
    try:
        with start_span(
            f"tool:{tool.name}",
            kind="INTERNAL",
            tool_name=tool.name,
            tool_call_id=call.id,
        ):
            result = await _invoke_with_recovery(view, tool, call, on_progress=on_progress)
    except CircuitOpenError:
        # Breaker state must not escape as an unhandled exception into the ReAct
        # loop; fold it into a text result for the LLM
        ok = False
        result = f"[熔断] {tool.name} 连续失败已暂停,请稍后重试"
    except (ConnectionError, httpx.ConnectError) as exc:
        ok = False
        result = (
            f"[积木服务离线] 工具 {tool.name} 所属的服务暂时不可用 (连接失败: {type(exc).__name__})。"
            "建议：该积木服务可能未启动或已断开，请尝试使用本地纯文本/文件工具替代，或提示用户检查服务状态。"
        )
    except FileNotFoundError as exc:
        ok = False
        if tool.name.startswith("mcp__") or "__" in tool.name:
            result = (
                f"[积木服务离线] 工具 {tool.name} 所需的外部运行环境或可执行文件未找到 ({exc})。"
                "建议：该积木运行环境缺失，请告知用户或使用本地其它工具替代。"
            )
        else:
            result = f"[工具失败] {tool.name}: {type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001  # tool failures go back to the LLM as text results
        ok = False
        result = f"[工具失败] {tool.name}: {type(exc).__name__}: {exc}"
    finally:
        if view.meter is not None:
            view.meter.record(
                MeterRecord(
                    kind="tool",
                    name=tool.name,
                    ms=(time.perf_counter() - start) * 1000,
                    ok=ok,
                )
            )
    if view.hooks is not None:
        # post_tool: fire on both success and failure so hooks see the call result
        await view.hooks.fire("post_tool", name=tool.name, ok=ok, result=result)
    outcome = normalize(tool.name, result)
    if view.recorder is not None:
        # Episodic trail: one row per executed call (rejections above never
        # reach here); the recorder owns truncation and never raises.
        view.recorder(tool.name, call.arguments, ok, outcome.text)
    if not ok:
        outcome = ToolResult(
            name=outcome.name,
            ok=False,
            text=outcome.text,
            title=outcome.title,
            metadata=dict(outcome.metadata),
        )
    if view.result_budget is not None:
        # Oversized-result spill (truncated preview + on-disk full output);
        # applied after stringify so every tool shares one budget path.
        # Identity check: the budget returns the same object when within
        # limit, so `is not` reliably detects a spill.
        budgeted = view.result_budget(outcome.text, tool.name)
        if budgeted is not outcome.text:
            metadata = dict(outcome.metadata)
            metadata["truncated"] = True
            outcome = ToolResult(
                name=outcome.name,
                ok=outcome.ok,
                text=budgeted,
                title=outcome.title,
                metadata=metadata,
            )
    return outcome
