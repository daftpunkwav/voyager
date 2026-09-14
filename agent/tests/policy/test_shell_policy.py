"""Tests for shell command-prefix permission rules: deny precedence,
allow-without-confirm for read-only commands, and the write-intent gate
that keeps prefix allows from becoming a write bypass.
"""

from agent.policy import Action, FsPolicy, PolicyEngine
from agent.policy.levels import Level
from agent.policy.shell import ShellPolicy, command_tokens


def _engine(**kw) -> PolicyEngine:
    return PolicyEngine(fs=FsPolicy(roots=("/ws",)), **kw)


def _shell_cmd(cmd: str):
    return Action(dimension="shell", target=cmd, write=True)


class TestCommandTokens:
    def test_parse_error_yields_no_tokens(self) -> None:
        assert command_tokens('git commit -m "unterminated') == ()

    def test_tokens_keep_quotes_on_windows_mode(self) -> None:
        assert command_tokens('git commit -m "hi"') == ("git", "commit", "-m", '"hi"')


class TestPrefixRules:
    def test_no_rules_defaults_to_confirm(self) -> None:
        decision = _engine().decide(_shell_cmd("git status"))
        assert decision.allow is True
        assert decision.level == Level.L2_CONFIRM

    def test_exact_pattern_requires_full_match(self) -> None:
        engine = _engine(shell=ShellPolicy(allowed=frozenset({"git status"})))
        assert engine.decide(_shell_cmd("git status")).level == Level.L0_SILENT
        # extra arguments are not covered by an exact pattern
        assert engine.decide(_shell_cmd("git status --short")).level == Level.L2_CONFIRM

    def test_trailing_star_covers_remaining_arguments(self) -> None:
        engine = _engine(shell=ShellPolicy(allowed=frozenset({"git diff *"})))
        assert engine.decide(_shell_cmd("git diff")).level == Level.L0_SILENT
        assert engine.decide(_shell_cmd("git diff HEAD~1")).level == Level.L0_SILENT
        assert engine.decide(_shell_cmd("git log")).level == Level.L2_CONFIRM

    def test_denied_rule_rejects(self) -> None:
        engine = _engine(shell=ShellPolicy(denied=frozenset({"rm *"})))
        decision = engine.decide(_shell_cmd("rm -rf build"))
        assert decision.allow is False

    def test_denied_wins_over_allowed(self) -> None:
        engine = _engine(shell=ShellPolicy(allowed=frozenset({"*"}), denied=frozenset({"curl *"})))
        assert engine.decide(_shell_cmd("curl example.com")).allow is False
        assert engine.decide(_shell_cmd("ls")).allow is True

    def test_unparseable_command_falls_back_to_confirm(self) -> None:
        engine = _engine(shell=ShellPolicy(allowed=frozenset({"*"})))
        assert engine.decide(_shell_cmd('git commit -m "oops')).level == Level.L2_CONFIRM


class TestWriteIntentGate:
    def test_allow_rule_never_covers_redirection(self) -> None:
        engine = _engine(shell=ShellPolicy(allowed=frozenset({"python *"})))
        assert engine.decide(_shell_cmd("python main.py > out.txt")).level == Level.L2_CONFIRM

    def test_allow_rule_never_covers_write_verbs(self) -> None:
        engine = _engine(shell=ShellPolicy(allowed=frozenset({"git *"})))
        # cp is not a git thing, but a crafted "git *" prefix must still not
        # launder a chained write command through the rule
        assert engine.decide(_shell_cmd("git log; cp a b")).level == Level.L2_CONFIRM

    def test_skills_write_denied_even_with_allow_all(self) -> None:
        engine = _engine(shell=ShellPolicy(allowed=frozenset({"*"})))
        decision = engine.decide(_shell_cmd("echo x > skills/keep/SKILL.md"))
        assert decision.allow is False


class TestWriteFlagGate:
    """A prefix allow rule must not launder flag-carried writes
    (`git diff --output=x`, `find -delete`, `sort -o out`)."""

    def _allow_engine(self, pattern: str) -> PolicyEngine:
        return _engine(shell=ShellPolicy(allowed=frozenset({pattern})))

    def test_output_flag_falls_back_to_confirm(self) -> None:
        engine = self._allow_engine("git diff *")
        decision = engine.decide(_shell_cmd("git diff HEAD --output=/tmp/x.patch"))
        assert decision.level == Level.L2_CONFIRM

    def test_delete_flag_falls_back_to_confirm(self) -> None:
        engine = self._allow_engine("find *")
        assert engine.decide(_shell_cmd("find . -name tmp -delete")).level == Level.L2_CONFIRM

    def test_short_output_flag_falls_back_to_confirm(self) -> None:
        engine = self._allow_engine("sort *")
        assert engine.decide(_shell_cmd("sort -o out.txt in.txt")).level == Level.L2_CONFIRM

    def test_dd_verb_counts_as_write_intent(self) -> None:
        engine = self._allow_engine("dd *")
        assert engine.decide(_shell_cmd("dd if=a of=/dev/sda")).level == Level.L2_CONFIRM

    def test_read_only_flags_still_allowed(self) -> None:
        engine = self._allow_engine("grep *")
        assert engine.decide(_shell_cmd("grep -n -i pattern file")).level == Level.L0_SILENT
