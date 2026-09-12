"""reach_out tool: send one proactive message to a chat session and finish
immediately (fire-and-forget; never stays resident waiting).

Agent-only by design (the human IS the recipient); declared in parity.py.
Anti-bombing: the tool shares the proactive engine's OutreachBudget, so a
prompt-injected spam loop hits the same daily/session caps and cooldown as
greetings and follow-ups; the app dimension makes the send visible (L1)
instead of silent.
"""

from __future__ import annotations

from typing import Any

from agent.tools.core.base import AgentTool

SessionSink = Any  # master.reply(text, session=...) awaitable


def reach_out_tool(reply: SessionSink, budget: Any | None = None) -> AgentTool:
    async def reach_out(session_id: str = "", text: str = "") -> dict | str:
        body = str(text or "").strip()
        if not body:
            return "[参数错误] text 不能为空"
        target = str(session_id or "")
        if budget is not None:
            decision = budget.allow(session=target)
            if not decision.allow:
                return f"[已拦截] 主动消息被防轰炸预算拒绝:{decision.reason}"
        await reply(body, session=target)
        if budget is not None:
            budget.record(session=target)
        return {"sent": True, "session": session_id}

    return AgentTool(
        name="reach_out",
        description=(
            "向某个会话主动发送一条消息后立即结束(发出即完成,不等待回复);"
            "用于异步任务的结果通报或定时提醒,消息会在用户的会话里出现"
        ),
        handler=reach_out,
        dimension="app",
        write=True,
        schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "目标会话 id(空 = 当前会话)"},
                "text": {"type": "string"},
            },
            "required": ["text"],
        },
    )


__all__ = ["reach_out_tool"]
