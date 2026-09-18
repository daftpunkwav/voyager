"""rate_turn capability: the user scores and comments a finished agent turn;
the verdict lands in memory so later turns inherit the guidance (resident
relevance layer surfaces it when the same subject comes up)."""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps

_VALID_SCORES = (1, 2, 3, 4, 5)


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="rate_turn",
        description="Rate a finished agent turn (1-5) with an optional comment; the verdict is stored as memory that guides future turns",
    )
    def rate_turn(score: int, comment: str = "", subject: str = "") -> dict:
        if score not in _VALID_SCORES:
            from platform_contracts import ErrorSuffix, ServiceError

            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"score must be one of {list(_VALID_SCORES)}",
            )
        stars = "★" * score + "☆" * (5 - score)
        text = f"{stars} {comment.strip()}".strip()
        topic = subject.strip()[:60] or "agent 执行"
        deps.memory.semantic.add(topic, "评价", text, source="feedback")
        deps.memory.episodic.log("feedback", f"{topic} 评分:{text}")
        return {"score": score, "subject": topic, "stored": True}
