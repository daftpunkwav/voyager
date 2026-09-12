"""Local session tokens: sign and verify HMAC-SHA256 tokens.

The signing secret file is created automatically on first startup under
data/runtime and is never regenerated afterwards.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from platform_contracts import ActorKind, ActorRef, ErrorSuffix, ServiceError

_DOMAIN = "actor"
_DEFAULT_TTL = 30 * 24 * 3600  # local tokens default to 30 days


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class LocalTokenIssuer:
    """Issue and verify local session tokens.

    The signing secret lives under data/runtime and is auto-generated on
    first startup with 0o600 permissions.
    """

    def __init__(self, secret_path: str | Path) -> None:
        self._path = Path(secret_path)
        self._secret = self._load_or_create()

    def _load_or_create(self) -> bytes:
        if self._path.exists():
            return bytes.fromhex(self._path.read_text(encoding="utf-8").strip())
        self._path.parent.mkdir(parents=True, exist_ok=True)
        secret = secrets.token_hex(32)
        # 0o600 takes effect on Unix only; Windows ignores the mode (known
        # platform limitation). Isolation there relies on the NTFS user
        # profile being private; Windows ACLs could harden this further.
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(secret)
        return bytes.fromhex(secret)

    def issue(self, actor: ActorRef, ttl_seconds: float = _DEFAULT_TTL) -> str:
        payload = {
            "kind": actor.kind.value,
            "id": actor.id,
            "scopes": list(actor.scopes),
            "exp": time.time() + ttl_seconds,
        }
        body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
        sig = _b64e(hmac.new(self._secret, body.encode(), hashlib.sha256).digest())
        return f"{body}.{sig}"

    def verify(self, token: str) -> ActorRef:
        try:
            body, sig = token.split(".")
            expected = _b64e(hmac.new(self._secret, body.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(sig, expected):
                raise ValueError("signature mismatch")
            payload = json.loads(_b64d(body))
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(_DOMAIN, ErrorSuffix.AUTH_REQUIRED, f"invalid token: {exc}") from exc
        if float(payload.get("exp", 0)) < time.time():
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.AUTH_REQUIRED,
                "token expired",
                hint="request a new local token",
            )
        return ActorRef(
            kind=ActorKind(payload["kind"]),
            id=str(payload["id"]),
            scopes=tuple(payload.get("scopes") or ()),
        )
