"""Unified error codes.

Codes have the form `<DOMAIN>.<SUFFIX>`: the domain is the upper-cased service
name (e.g. ``EXAMPLE``) and the suffix is one of the generic suffixes defined here.
Every error body is {"error": {"code", "message", "service", "hint",
"trace_id"}}. This package defines only codes and their HTTP mapping, not any
domain-specific errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ErrorSuffix(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"  # service unavailable
    QUEUE_FULL = "QUEUE_FULL"  # queue full, retry later
    NOT_FOUND = "NOT_FOUND"
    AUTH_REQUIRED = "AUTH_REQUIRED"  # not authenticated
    FORBIDDEN = "FORBIDDEN"  # authenticated but not authorized
    RATE_LIMITED = "RATE_LIMITED"  # rate limit / quota exhausted
    INVALID_INPUT = "INVALID_INPUT"
    CONFLICT = "CONFLICT"
    INTERNAL = "INTERNAL"


#: Error-code suffix to HTTP status mapping
HTTP_STATUS: dict[ErrorSuffix, int] = {
    ErrorSuffix.UNAVAILABLE: 503,
    ErrorSuffix.QUEUE_FULL: 429,
    ErrorSuffix.NOT_FOUND: 404,
    ErrorSuffix.AUTH_REQUIRED: 401,
    ErrorSuffix.FORBIDDEN: 403,
    ErrorSuffix.RATE_LIMITED: 429,
    ErrorSuffix.INVALID_INPUT: 400,
    ErrorSuffix.CONFLICT: 409,
    ErrorSuffix.INTERNAL: 500,
}


def make_code(domain: str, suffix: ErrorSuffix) -> str:
    """Assemble an error code: make_code("example", UNAVAILABLE) -> "EXAMPLE.UNAVAILABLE"."""
    return f"{domain.strip().upper().replace('-', '_')}.{suffix.value}"


#: Machine-readable hint marking a context-window overflow (the transcript
#: exceeds the model's context). Domains set this as the ServiceError hint so
#: adapters and the agent loop can tell "compact and retry" apart from a
#: generic bad request.
CONTEXT_OVERFLOW_HINT = "context_overflow"


@dataclass(frozen=True)
class ErrorBody:
    code: str
    message: str
    service: str
    hint: str = ""  # actionable hint (e.g. "retry later from the settings page")
    trace_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "service": self.service,
            "hint": self.hint,
            "trace_id": self.trace_id,
        }


@dataclass(frozen=True)
class ErrorEnvelope:
    error: ErrorBody

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.error.to_dict()}


class ServiceError(Exception):
    """Exception carrying an ErrorBody.

    Raised by services or frameworks at any point; boundaries map it to an
    HTTP or MCP error response.
    """

    def __init__(
        self,
        domain: str,
        suffix: ErrorSuffix,
        message: str,
        *,
        hint: str = "",
        trace_id: str = "",
    ) -> None:
        super().__init__(message)
        self.body = ErrorBody(
            code=make_code(domain, suffix),
            message=message,
            service=domain,
            hint=hint,
            trace_id=trace_id,
        )

    @property
    def http_status(self) -> int:
        suffix = self.body.code.rsplit(".", 1)[-1]
        try:
            return HTTP_STATUS[ErrorSuffix(suffix)]
        except ValueError:
            return 500

    def to_envelope(self) -> dict[str, Any]:
        return ErrorEnvelope(error=self.body).to_dict()
