"""Tests for the post-confirm shell dimension: skills-subtree and read-only
root guards still hard-reject, unparseable commands still execute (no rule
matching left), and the reported default level stays L2 for intent
visibility (invoke.py no longer confirms it)."""

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

    def test_tokens_are_unquoted_and_case_folded(self) -> None:
        """posix=False keeps quote characters and original case on the raw
        tokens; command_tokens normalizes both so quoting shapes and Windows'
        case-insensitive binary resolution cannot dodge a deny prefix."""
        assert command_tokens('git commit -m "hi"') == ("git", "commit", "-m", "hi")
        assert command_tokens('"git" PUSH') == ("git", "push")


class TestGuards:
    def test_skills_write_still_rejected(self) -> None:
        decision = _engine().decide(_shell_cmd("echo x > skills/keep/SKILL.md"))
        assert decision.allow is False

    def test_skills_delete_verb_still_rejected(self) -> None:
        decision = _engine().decide(_shell_cmd("rm skills/keep/SKILL.md"))
        assert decision.allow is False

    def test_readonly_root_write_via_shell_rejected(self) -> None:
        engine = PolicyEngine(
            fs=FsPolicy(roots=("/ws",), read_roots=("/data/ro",)), shell=ShellPolicy()
        )
        decision = engine.decide(_shell_cmd("cp a /data/ro/b"))
        assert decision.allow is False

    def test_skills_write_denied_even_in_full_mode(self) -> None:
        decision = _engine(shell=ShellPolicy()).decide(_shell_cmd("echo x > skills/keep/SKILL.md"))
        assert decision.allow is False


class TestDefaultLevel:
    def test_default_reports_l2_but_executes(self) -> None:
        """The reported level stays L2 for intent visibility; invoke.py no
        longer confirms it (the confirm channel retired)."""
        decision = _engine().decide(_shell_cmd("git status"))
        assert decision.allow is True
        assert decision.level == Level.L2_CONFIRM
