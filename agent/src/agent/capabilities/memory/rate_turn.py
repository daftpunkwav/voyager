"""rate_turn capability: the user scores and comments a finished agent turn;
the verdict lands in memory so later turns inherit the guidance (resident
relevance layer surfaces it when the same subject comes up)."""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps

_VALID_SCORES = (1, 2, 3, 4, 5)


#: Facts surface back into prompts via recall, so a comment is capped like
#: the distiller caps extracted content (400 chars) instead of storing blobs.
_MAX_COMMENT_CHARS = 400


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="rate_turn",
        description="Rate a finished agent turn (1-5) with an optional comment; the verdict is stored as memory that guides future turns",
    )
    def rate_turn(score: int, comment: str = "", subject: str = "") -> dict:
        # No input_model: this handler is its own validator (repo convention).
        # bool is an int subclass, and a float like 1.0 would pass the membership
        # check below but crash the star rendering - reject both up front.
        if isinstance(score, bool) or not isinstance(score, int) or score not in _VALID_SCORES:
            from platform_contracts import ErrorSuffix, ServiceError

            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"score must be one of {list(_VALID_SCORES)}",
            )
        stars = "★" * score + "☆" * (5 - score)
        text = f"{stars} {comment.strip()[:_MAX_COMMENT_CHARS]}".strip()
        topic = subject.strip()[:60] or "agent 执行"
        deps.memory.semantic.add(topic, "评价", text, source="feedback")
        deps.memory.episodic.log("feedback", f"{topic} 评分:{text}")
        return {"score": score, "subject": topic, "stored": True}
