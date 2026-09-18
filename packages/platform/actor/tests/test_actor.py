"""Tests for actor facilities: token issue/verify/tamper/expiry, narrowing,
loopback.
"""

import base64
import hashlib
import hmac
import json
import time

import pytest
from platform_actor import ActorContext, LocalTokenIssuer, is_loopback
from platform_contracts import ActorKind, ActorRef, ServiceError

AGENT = ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=("graph.read", "notes.write"))


def _signed_token(issuer: LocalTokenIssuer, payload: dict) -> str:
    """Craft a correctly-signed token with arbitrary payload fields (the
    signature path mirrors issuer.issue)."""
    body = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .rstrip(b"=")
        .decode()
    )
    sig = (
        base64.urlsafe_b64encode(hmac.new(issuer._secret, body.encode(), hashlib.sha256).digest())
        .rstrip(b"=")
        .decode()
    )
    return f"{body}.{sig}"


@pytest.fixture()
def issuer(tmp_path):
    return LocalTokenIssuer(tmp_path / "secrets" / "machine.token")


class TestToken:
    def test_issue_verify_roundtrip(self, issuer) -> None:
        token = issuer.issue(AGENT)
        restored = issuer.verify(token)
        assert restored == AGENT

    def test_secret_persists_across_instances(self, tmp_path) -> None:
        path = tmp_path / "secrets" / "machine.token"
        token = LocalTokenIssuer(path).issue(AGENT)
        assert LocalTokenIssuer(path).verify(token) == AGENT  # secret survives restarts

    def test_tampered_signature_rejected(self, issuer) -> None:
        token = issuer.issue(AGENT)
        body, _sig = token.split(".")
        forged = body + "." + "A" * 43
        with pytest.raises(ServiceError) as exc:
            issuer.verify(forged)
        assert exc.value.body.code == "ACTOR.AUTH_REQUIRED"
        assert exc.value.http_status == 401

    def test_expired_rejected(self, issuer) -> None:
        token = issuer.issue(AGENT, ttl_seconds=-1)
        with pytest.raises(ServiceError, match="expired"):
            issuer.verify(token)

    def test_garbage_rejected(self, issuer) -> None:
        with pytest.raises(ServiceError):
            issuer.verify("not-a-token")

    @pytest.mark.parametrize(
        "payload",
        [
            {"kind": "bogus", "id": "x", "scopes": [], "exp": time.time() + 60},  # bad kind
            {"id": "x", "scopes": []},  # kind missing
            {"kind": "agent", "id": "x", "exp": "soon"},  # non-numeric exp
        ],
    )
    def test_malformed_signed_payload_is_401_not_500(self, issuer, payload) -> None:
        """A correctly-signed token with malformed fields is an auth failure
        (ServiceError/401), never a leaking ValueError/KeyError (500)."""
        with pytest.raises(ServiceError) as exc:
            issuer.verify(_signed_token(issuer, payload))
        assert exc.value.body.code == "ACTOR.AUTH_REQUIRED"
        assert exc.value.http_status == 401


class TestContext:
    def test_trace_id_generated(self) -> None:
        assert ActorContext(actor=AGENT).trace_id

    def test_restrict_intersection(self) -> None:
        ctx = ActorContext(actor=AGENT)
        narrowed = ctx.restrict(["graph.read", "settings.write"])
        assert narrowed.actor.scopes == ("graph.read",)  # unheld settings.write is dropped
        assert narrowed.trace_id == ctx.trace_id

    def test_wildcard_restrict(self) -> None:
        admin = ActorRef(kind=ActorKind.AGENT, id="a", scopes=("*",))
        narrowed = ActorContext(actor=admin).restrict(["notes.write"])
        assert narrowed.actor.scopes == ("notes.write",)

    def test_has_scope(self) -> None:
        ctx = ActorContext(actor=AGENT)
        assert ctx.has_scope("graph.read")
        assert not ctx.has_scope("llm.admin")


class _Req:
    def __init__(self, host: str) -> None:
        self.client = type("C", (), {"host": host})()


class TestLoopback:
    def test_ipv4_mapped_and_names(self) -> None:
        assert is_loopback(_Req("127.0.0.1"))
        assert is_loopback(_Req("::1"))
        assert is_loopback(_Req("::ffff:127.0.0.1"))
        assert is_loopback(_Req("localhost"))
        assert is_loopback(_Req("testclient"))
        assert not is_loopback(_Req("10.0.0.8"))
        assert not is_loopback(_Req("::ffff:10.0.0.8"))
