"""D-10 verification: secret values never reach the audit trail in
readable form — the framework redacts sensitive-argument names at the call
boundary (summarize_args), and set_api_key writes the key into
platform_secrets instead of any log or settings row. Handlers still receive
raw values (single implementation today); the credential-reference refactor
stays deferred (ruling recorded in docs-local/phases/21-security.md).
"""

from __future__ import annotations

from platform_capability.guards import SENSITIVE_KEYS, summarize_args


class TestRedaction:
    def test_sensitive_keys_are_redacted_in_audit_summaries(self) -> None:
        args = {
            "provider_id": "p1",
            "api_key": "sk-super-secret-value",
            "Authorization": "Bearer abc",
            "password": "hunter2",
        }
        summary = summarize_args(args)
        assert "sk-super-secret-value" not in summary
        assert "hunter2" not in summary
        assert "Bearer abc" not in summary
        assert "***" in summary
        assert "p1" in summary  # non-sensitive values stay readable

    def test_sensitive_vocabulary_is_frozen(self) -> None:
        # The word list guards every capability call's audit summary; growing
        # it is a deliberate security diff.
        assert set(SENSITIVE_KEYS) == {
            "api_key",
            "api-key",
            "apikey",
            "token",
            "secret",
            "password",
            "authorization",
            "credential",
        }

    def test_case_insensitive_match(self) -> None:
        summary = summarize_args({"API_KEY": "leak", "X-Token": "leak", "My_Credential": "leak"})
        assert "leak" not in summary
