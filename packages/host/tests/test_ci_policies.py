"""Supply-chain policy of the CI workflows and the npm scripts.

The install and audit commands are the supply-chain boundary of this
repository: they decide which package versions run, whether an install
script may execute and whether a download may leave HTTPS. Nothing in the
runtime suite observes them, so a change that dropped one of these guards
would leave the whole suite green. The policy is asserted here instead.
"""

import ast
import json
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

CI_WORKFLOW = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
SECURITY_WORKFLOW = (ROOT / ".github/workflows/security.yml").read_text(encoding="utf-8")
PACKAGE_JSON = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
UV_LOCK = (ROOT / "uv.lock").read_text(encoding="utf-8")
AUDIT_SCRIPT = (ROOT / "scripts/pip_audit.py").read_text(encoding="utf-8")


def _commands(workflow: str, needle: str) -> list[str]:
    """The workflow lines that run `needle`, comments left out."""
    found: list[str] = []
    for line in workflow.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if needle in stripped:
            found.append(stripped)
    return found


def _matches(path: str, pattern: str) -> bool:
    """Whether a path matches one of the alternatives of a shell pattern list."""
    return any(fnmatch(path, alternative) for alternative in pattern.split("|"))


def _triage_patterns(workflow: str) -> dict[str, str]:
    """The path patterns the changed-path triage matches against.

    The `changes` job classifies a changed path in a shell case statement:
    the pattern sits on the line above the flag it sets.
    """
    patterns: dict[str, str] = {}
    lines = workflow.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        for flag in ("py", "web"):
            if stripped != f"{flag}=true ;;":
                continue
            pattern = lines[index - 1].strip().removeprefix("(").removesuffix(")")
            patterns[flag] = pattern
    return patterns


def _uv_invocations(script: str, subcommand: str) -> list[list[str]]:
    """The argument vectors of the `uv <subcommand>` calls in the script.

    The audit script calls `uv` twice: once to export the resolution and
    once to run the audit tool. Every call is read on its own, so one
    invocation cannot pass the check on the strength of the other.
    """
    invocations: list[list[str]] = []
    for node in ast.walk(ast.parse(script)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "run":
            continue
        if not isinstance(func.value, ast.Name) or func.value.id != "subprocess":
            continue
        if not node.args or not isinstance(node.args[0], ast.List):
            continue
        argv = [
            element.value
            for element in node.args[0].elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        ]
        if len(argv) >= 2 and argv[0] == "uv" and argv[1] == subcommand:
            invocations.append(argv)
    return invocations


class TestLockedResolution:
    def test_python_installs_use_the_locked_versions(self) -> None:
        commands = _commands(CI_WORKFLOW, "uv sync") + _commands(CI_WORKFLOW, "uv run")
        assert commands, "the workflow no longer installs the Python workspace"
        for command in commands:
            for invocation in command.split("&&"):
                if "uv " in invocation:
                    assert "--locked" in invocation, invocation

    def test_npm_scripts_run_python_tools_from_the_locked_environment(self) -> None:
        scripts: dict[str, str] = PACKAGE_JSON["scripts"]
        callers = {name: script for name, script in scripts.items() if "uv run" in script}
        assert callers, "no npm script runs the Python tooling any more"
        for name, script in callers.items():
            for invocation in script.split("&&"):
                if "uv run" in invocation:
                    assert "--locked" in invocation, f"{name}: {invocation}"


class TestDisabledInstallScripts:
    def test_node_installs_disable_lifecycle_scripts(self) -> None:
        commands = _commands(CI_WORKFLOW, "npm ci")
        assert commands, "the workflow no longer installs the Node workspace"
        for command in commands:
            assert "--ignore-scripts" in command, command

    def test_playwright_comes_from_the_installed_workspace(self) -> None:
        assert "node_modules/.bin/playwright install" in CI_WORKFLOW
        assert not _commands(CI_WORKFLOW, "npx ")


class TestAuditTool:
    def test_audit_export_reads_the_committed_lockfile(self) -> None:
        """The scanned requirements must be the committed resolution, so the
        export may not re-resolve the dependencies it writes."""
        exports = _uv_invocations(AUDIT_SCRIPT, "export")
        assert exports, "the audit script no longer exports the resolution"
        for argv in exports:
            assert "--locked" in argv, argv

    def test_audit_tool_runs_from_the_locked_environment(self) -> None:
        """The audit tool must come from the locked environment, so the run
        may not re-resolve the tool and its dependencies."""
        runs = _uv_invocations(AUDIT_SCRIPT, "run")
        assert runs, "the audit script no longer runs the audit tool"
        for argv in runs:
            assert "--locked" in argv, argv
            assert "pip-audit" in argv, argv
        assert "uvx" not in AUDIT_SCRIPT

    def test_audit_tool_is_covered_by_the_committed_lockfile(self) -> None:
        assert 'name = "pip-audit"' in UV_LOCK

    def test_audit_tool_version_is_pinned_in_the_manifest(self) -> None:
        assert "pip-audit==" in PYPROJECT


class TestHttpsOnlyDownloads:
    def test_release_downloads_pin_https_and_tls(self) -> None:
        commands = _commands(SECURITY_WORKFLOW, "curl ")
        assert commands, "the security workflow no longer downloads the release"
        for command in commands:
            assert "--proto '=https'" in command, command
            assert "--proto-redir '=https'" in command, command
            assert "--tlsv1.2" in command, command

    def test_workflow_requests_stay_on_the_local_host(self) -> None:
        for command in _commands(CI_WORKFLOW, "curl "):
            assert "127.0.0.1" in command or "localhost" in command, command


class TestChangedPathTriage:
    def test_root_package_json_runs_the_python_gate(self) -> None:
        """The root manifest holds the npm scripts that call the Python
        tooling, so a change to it belongs to the Python gate."""
        patterns = _triage_patterns(CI_WORKFLOW)
        assert _matches("package.json", patterns["py"])
        assert _matches("package.json", patterns["web"])

    def test_python_and_web_paths_stay_classified(self) -> None:
        patterns = _triage_patterns(CI_WORKFLOW)
        assert _matches("scripts/pip_audit.py", patterns["py"])
        assert _matches("pyproject.toml", patterns["py"])
        assert _matches("apps/web/src/main.tsx", patterns["web"])
        assert not _matches("apps/web/src/main.tsx", patterns["py"])
