"""Supply-chain policy of the CI workflows and the npm scripts.

The install and audit commands are the supply-chain boundary of this
repository: they decide which package versions run, whether an install
script may execute and whether a download may leave HTTPS. Nothing in the
runtime suite observes them, so a change that dropped one of these guards
would leave the whole suite green. The policy is asserted here instead.
"""

import ast
import json
import tomllib
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]

CI_WORKFLOW = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
SECURITY_WORKFLOW = (ROOT / ".github/workflows/security.yml").read_text(encoding="utf-8")
PACKAGE_JSON = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
APP_PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
APP_UV_LOCK = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
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


def _script_constants(script: str) -> dict[str, str]:
    """The module level string constants of a script."""
    constants: dict[str, str] = {}
    for node in ast.parse(script).body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                constants[target.id] = node.value.value
    return constants


def _element_text(element: ast.expr) -> str:
    """The source text of one argv element.

    A string literal is its content, every other expression is unparsed
    (`str(reqs)`): two invocations are compared word by word, so the text
    the script runs is what counts, not the value of a constant.
    """
    if isinstance(element, ast.Constant) and isinstance(element.value, str):
        return element.value
    return ast.unparse(element)


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
        argv = [_element_text(element) for element in node.args[0].elts]
        if len(argv) >= 2 and argv[0] == "uv" and argv[1] == subcommand:
            invocations.append(argv)
    return invocations


def _flag_value(argv: list[str], flag: str) -> str | None:
    """The word that follows a flag, or None when the flag is absent."""
    for index, argument in enumerate(argv):
        if argument == flag and index + 1 < len(argv):
            return argv[index + 1]
    return None


def _audit_project() -> Path:
    """The project the audit script runs the audit tool in.

    The path comes from the script, so the policy is asserted on the
    project that actually runs the tool.
    """
    runs = _uv_invocations(AUDIT_SCRIPT, "run")
    assert runs, "the audit script no longer runs the audit tool"
    project = _flag_value(runs[0], "--project")
    assert project is not None, f"the audit tool no longer runs in its own project: {runs[0]}"
    constants = _script_constants(AUDIT_SCRIPT)
    return (ROOT / constants.get(project, project)).resolve()


def _audit_manifest() -> dict[str, Any]:
    """The manifest of the audit project."""
    return tomllib.loads((_audit_project() / "pyproject.toml").read_text(encoding="utf-8"))


def _audit_lock() -> dict[str, Any]:
    """The committed lockfile of the audit project."""
    return tomllib.loads((_audit_project() / "uv.lock").read_text(encoding="utf-8"))


def _lock_packages(lock: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The packages a lockfile resolves, name -> package entry."""
    return {package["name"]: package for package in lock.get("package", [])}


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

    def test_audit_tool_runs_in_an_isolated_project(self) -> None:
        """The tool may not run in the root project: there the run would
        install the application dependencies and the default dev group
        next to it."""
        runs = _uv_invocations(AUDIT_SCRIPT, "run")
        assert runs, "the audit script no longer runs the audit tool"
        for argv in runs:
            assert _flag_value(argv, "--project") is not None, argv
        project = _audit_project()
        assert project != ROOT, project
        # The audit project is excluded from the workspace, so it keeps its
        # own lockfile instead of sharing the root one.
        assert "tools/audit" in APP_PYPROJECT["tool"]["uv"]["workspace"]["exclude"]

    def test_audit_tool_is_covered_by_the_committed_lockfile(self) -> None:
        """The tool runs from the lockfile of its own project."""
        assert "pip-audit" in _lock_packages(_audit_lock())

    def test_audit_tool_version_is_pinned_in_the_manifest(self) -> None:
        """The audit gate runs code, so the tool is pinned to an exact
        version."""
        pins = _audit_manifest()["dependency-groups"]["audit"]
        assert any(pin.startswith("pip-audit==") for pin in pins), pins

    def test_audit_tool_is_declared_in_the_audit_group(self) -> None:
        """`uv run --group audit` finds the tool only in the audit group of
        the project the script runs in, and the lockfile of that project
        must resolve the group."""
        manifest = _audit_manifest()
        pins = manifest["dependency-groups"]["audit"]
        matches = [pin for pin in pins if pin.startswith("pip-audit==")]
        assert matches, f"the audit group declares no pinned audit tool: {pins}"
        version = matches[0].removeprefix("pip-audit==")

        packages = _lock_packages(_audit_lock())
        assert "pip-audit" in packages, sorted(packages)
        assert packages["pip-audit"]["version"] == version

        # The locked group resolution names the same pin.
        root = packages[manifest["project"]["name"]]
        requires = root["metadata"]["requires-dev"]["audit"]
        assert {"name": "pip-audit", "specifier": f"=={version}"} in requires, requires

    def test_the_application_project_does_not_ship_the_audit_tool(self) -> None:
        """The tool lives in its own project: the application lockfile must
        not resolve it, or the audit run would install it next to the
        application dependencies."""
        assert "pip-audit" not in _lock_packages(APP_UV_LOCK)


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
