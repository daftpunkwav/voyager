"""Note field validation: title, content length, tag characters."""

from __future__ import annotations

from platform_contracts import ErrorSuffix, ServiceError

# Import from the leaf constants module, not runtime, to avoid an import cycle.
from .domain import DOMAIN

MAX_TITLE = 200
MAX_CONTENT = 200_000
MAX_IMPORT_BYTES = MAX_CONTENT * 4
MAX_SOURCE_ID = 80
TAG_FORBIDDEN = '"\\,[]'


def validate_title(title: str) -> str:
    title = (title or "").strip()
    if not title:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT, "Title cannot be empty")
    if len(title) > MAX_TITLE:
        raise ServiceError(
            DOMAIN, ErrorSuffix.INVALID_INPUT, f"Title too long (≤{MAX_TITLE} chars)"
        )
    return title


def validate_content(content: str | None) -> None:
    if content is not None and len(content) > MAX_CONTENT:
        raise ServiceError(
            DOMAIN, ErrorSuffix.INVALID_INPUT, f"Content too long (≤{MAX_CONTENT} chars)"
        )


def validate_tag(tag: str) -> str:
    tag = (tag or "").strip()
    if not tag or any(ch in TAG_FORBIDDEN for ch in tag):
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            f"Tag is empty or contains forbidden characters ({TAG_FORBIDDEN}): {tag!r}",
        )
    if len(tag) > 32:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT, "Tag too long (≤32 chars)")
    return tag


def validate_source_id(source_id: str) -> str:
    """source_id/node_id allow only safe identifiers; path traversal is rejected."""
    sid = str(source_id or "").strip()
    if not sid:
        return ""
    if "/" in sid or "\\" in sid or ".." in sid or len(sid) > MAX_SOURCE_ID:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT, "Invalid source_id or node_id")
    return sid


def validate_node_id(node_id: str) -> str:
    return validate_source_id(node_id)
