"""Supply-chain policy of the CI workflows and the npm scripts.

The install and audit commands are the supply-chain boundary of this
repository: they decide which package versions run, whether an install
script may execute and whether a download may leave HTTPS. Nothing in the
runtime suite observes them, so a change that dropped one of these guards
would leave the whole suite green. The policy is asserted here instead.
"""

import ast
import json
import shlex
import tomllib
from fnmatch import fnmatch
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]

CI_WORKFLOW = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
SECURITY_WORKFLOW = (ROOT / ".github/workflows/security.yml").read_text(encoding="utf-8")
PACKAGE_JSON = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
APP_PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
APP_UV_LOCK = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
AUDIT_SCRIPT = (ROOT / "scripts/pip_audit.py").read_text(encoding="utf-8")

# The client program of an HTTP request does not matter for the policy:
# curl, wget and the httpie front ends all leave the machine.
REQUEST_TOOLS = frozenset({"curl", "wget", "http", "https", "aria2c", "httpie"})
# The hosts a workflow request may reach.
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
# The npm scripts that run the Python tooling. Every one of them has to
# reach the interpreter through `uv run`, so the locked environment
# provides the tool and its dependencies.
PYTHON_TOOLING_SCRIPTS = frozenset(
    {
        "audit:py",
        "docs:i18n",
        "docs:links",
        "eval",
        "eval:update",
        "graph",
        "graph:check",
        "lint:imports",
        "lint:py",
        "test:py",
        "typecheck:py",
    }
)


def _commands(workflow: str, needle: str) -> list[str]:
    """The workflow commands that run `needle`, comments left out.

    A step writes its command after `run:`, so the prefix is dropped
    before the line is parsed as a shell command.
    """
    found: list[str] = []
    for line in workflow.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if needle in stripped:
            found.append(stripped.removeprefix("run:").strip())
    return found


def _argv(command: str) -> list[str]:
    """The words of one shell command, comments removed.

    A flag in a trailing comment is not an argument: `uv sync # --locked`
    locks nothing, so the flags are read from the parsed words and not
    from the raw text.
    """
    try:
        return shlex.split(command, comments=True)
    except ValueError as error:
        raise AssertionError(f"unparsable shell command: {command!r} ({error})") from error


def _chain(command: str) -> list[str]:
    """The individual commands of a shell chain.

    The chain operators (&&, ||, ; and |) end a command, so every link
    is parsed on its own: a guarded command does not vouch for the
    fallback that follows it. Quoted text stays in one piece.
    """
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(command):
        char = command[index]
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
            current.append(char)
        elif command[index : index + 2] in ("&&", "||"):
            parts.append("".join(current))
            current = []
            index += 2
            continue
        elif char in ";|":
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def _command_argvs(command: str) -> list[list[str]]:
    """The argument vectors of every command of a shell chain."""
    return [_argv(part) for part in _chain(command)]


def _uv_commands(command: str) -> list[list[str]]:
    """The argument vectors of the uv invocations of one shell command."""
    return [argv for argv in _command_argvs(command) if argv and argv[0] == "uv"]


def _assert_expected_python_tooling_scripts() -> None:
    """Every expected Python-tooling script runs through `uv run`.

    A script that calls the interpreter directly leaves the set of
    scripts that run through uv, so the expected scripts are named
    here: the policy holds only while every one of them is in the set.
    """
    scripts: dict[str, str] = PACKAGE_JSON["scripts"]
    callers = {name for name, script in scripts.items() if "uv run" in script}
    assert callers, "no npm script runs the Python tooling any more"
    missing = sorted(PYTHON_TOOLING_SCRIPTS - callers)
    assert not missing, f"the Python tooling scripts left the locked environment: {missing}"


def _flag_value(argv: list[str], flag: str) -> str | None:
    """The word that follows a flag, or None when the flag is absent."""
    for index, argument in enumerate(argv):
        if argument == flag and index + 1 < len(argv):
            return argv[index + 1]
    return None


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

    The audit script exports the application resolution and the locked
    dependency set of the audit tooling, and runs the audit tool over
    both of them. Every call is read on its own, so one invocation
    cannot pass the check on the strength of the other.
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


def _audit_tool_group() -> str:
    """The dependency group of the audit project that pins the audit tool."""
    groups = _audit_manifest().get("dependency-groups", {})
    pinned = [
        name for name, pins in groups.items() if any(pin.startswith("pip-audit==") for pin in pins)
    ]
    assert len(pinned) == 1, f"the audit project pins the audit tool in {pinned}"
    return pinned[0]


def _selected_group(argv: list[str]) -> str | None:
    """The dependency group an audit invocation selects.

    The group is named by a constant of the script, so the constant is
    resolved to the group the run actually selects.
    """
    value = _flag_value(argv, "--group")
    if value is None:
        return None
    return _script_constants(AUDIT_SCRIPT).get(value, value)


def _audit_lock() -> dict[str, Any]:
    """The committed lockfile of the audit project."""
    return tomllib.loads((_audit_project() / "uv.lock").read_text(encoding="utf-8"))


def _lock_packages(lock: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The packages a lockfile resolves, name -> package entry."""
    return {package["name"]: package for package in lock.get("package", [])}


def _request_commands(workflow: str) -> list[tuple[str, list[str]]]:
    """The HTTP request commands of a workflow and their target URLs.

    The client program does not matter (curl, wget, http, ...): the policy
    is about the host a request reaches, so every tool that can issue one
    is inspected.
    """
    requests: list[tuple[str, list[str]]] = []
    for line in workflow.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if not any(token.strip(";&|()") in REQUEST_TOOLS for token in stripped.split()):
            continue
        argv = _argv(stripped)
        urls = [token for token in argv if token.startswith(("http://", "https://"))]
        requests.append((stripped, urls))
    return requests


class TestLockedResolution:
    def test_python_installs_use_the_locked_versions(self) -> None:
        commands = _commands(CI_WORKFLOW, "uv sync") + _commands(CI_WORKFLOW, "uv run")
        assert commands, "the workflow no longer installs the Python workspace"
        for command in commands:
            invocations = _uv_commands(command)
            assert invocations, f"the workflow no longer runs uv: {command}"
            for argv in invocations:
                assert "--locked" in argv, (command, argv)

    def test_npm_scripts_run_python_tools_from_the_locked_environment(self) -> None:
        """The Python tooling runs from the locked environment: every uv
        invocation of an npm script carries the locked flag, and every
        expected script is one of those invocations."""
        _assert_expected_python_tooling_scripts()
        for name, script in PACKAGE_JSON["scripts"].items():
            for argv in _uv_commands(script):
                assert "--locked" in argv, f"{name}: {argv}"

    def test_npm_scripts_do_not_call_the_interpreter_directly(self) -> None:
        """The interpreter is reached through the locked environment only:
        a direct call resolves and installs on its own."""
        for name, script in PACKAGE_JSON["scripts"].items():
            for argv in _command_argvs(script):
                if not argv:
                    continue
                assert argv[0] not in {"python", "python3"}, f"{name}: {argv}"


class TestDisabledInstallScripts:
    def test_node_installs_disable_lifecycle_scripts(self) -> None:
        commands = _commands(CI_WORKFLOW, "npm ci")
        assert commands, "the workflow no longer installs the Node workspace"
        for command in commands:
            assert "--ignore-scripts" in _argv(command), command

    def test_playwright_comes_from_the_installed_workspace(self) -> None:
        assert "node_modules/.bin/playwright install" in CI_WORKFLOW
        assert not _commands(CI_WORKFLOW, "npx ")


class TestNoSourceBuilds:
    """A source distribution is built by its own build backend, so an
    install may never build one: the backend of a third-party package
    would run during the install."""

    def test_workflow_installs_do_not_build_source_distributions(self) -> None:
        commands = _commands(CI_WORKFLOW, "uv sync") + _commands(CI_WORKFLOW, "uv run")
        assert commands, "the workflow no longer installs the Python workspace"
        for command in commands:
            invocations = _uv_commands(command)
            assert invocations, f"the workflow no longer runs uv: {command}"
            for argv in invocations:
                assert "--no-build" in argv, (command, argv)

    def test_npm_scripts_do_not_build_source_distributions(self) -> None:
        _assert_expected_python_tooling_scripts()
        for name, script in PACKAGE_JSON["scripts"].items():
            for argv in _uv_commands(script):
                assert "--no-build" in argv, f"{name}: {argv}"

    def test_the_audit_tool_runs_without_building_source_distributions(self) -> None:
        runs = _uv_invocations(AUDIT_SCRIPT, "run")
        assert runs, "the audit script no longer runs the audit tool"
        for argv in runs:
            assert "--no-build" in argv, argv


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

    def test_audit_tool_runs_from_the_selected_dependency_group(self) -> None:
        """The tool lives in a dependency group, and a clean runner installs
        the default groups only: the run has to select the group that
        holds the tool, and that group has to be the one the manifest
        pins the tool in."""
        runs = _uv_invocations(AUDIT_SCRIPT, "run")
        assert runs, "the audit script no longer runs the audit tool"
        group = _audit_tool_group()
        for argv in runs:
            assert _selected_group(argv) == group, argv

    def test_audit_scans_the_exported_requirements(self) -> None:
        """The exported set must be the scanned set: the export writes and
        the audit reads the same file."""
        exports = _uv_invocations(AUDIT_SCRIPT, "export")
        runs = _uv_invocations(AUDIT_SCRIPT, "run")
        assert exports, "the audit script no longer exports the resolution"
        assert runs, "the audit script no longer runs the audit tool"
        scanned = {_flag_value(run, "-r") for run in runs}
        for export in exports:
            written = _flag_value(export, "-o")
            assert written is not None, export
            assert written in scanned, (export, runs)

    def test_the_audit_tooling_is_scanned_as_well(self) -> None:
        """The audit tooling runs while the scan runs, so a vulnerability in
        it is reachable during the scan: its locked dependency set is
        exported and scanned like the application set."""
        exports = _uv_invocations(AUDIT_SCRIPT, "export")
        runs = _uv_invocations(AUDIT_SCRIPT, "run")
        assert exports, "the audit script no longer exports the resolution"
        assert runs, "the audit script no longer runs the audit tool"
        project = _flag_value(runs[0], "--project")
        assert project is not None, runs[0]
        tooling_exports = [argv for argv in exports if _flag_value(argv, "--project") == project]
        assert tooling_exports, f"the audit tooling is not exported: {exports}"
        for export in tooling_exports:
            assert "--locked" in export, export
            assert _selected_group(export) == _audit_tool_group(), export

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
            argv = _argv(command)
            assert _flag_value(argv, "--proto") == "=https", command
            assert _flag_value(argv, "--proto-redir") == "=https", command
            assert "--tlsv1.2" in argv, command

    def test_workflow_requests_stay_on_the_local_host(self) -> None:
        """Every request of the CI workflow must stay on the local host: the
        release downloads of the security workflow are a separate concern
        (test_release_downloads_pin_https_and_tls)."""
        requests = _request_commands(CI_WORKFLOW)
        assert requests, "the workflow no longer issues a request"
        for command, urls in requests:
            assert urls, f"request without a target URL: {command}"
            for url in urls:
                host = urlparse(url).hostname
                assert host in LOCAL_HOSTS, f"{command} -> {url}"


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

    def test_the_audit_project_runs_the_python_gate(self) -> None:
        """The audit project holds the audit tool and its own lockfile, and
        the audit policy is asserted by the Python gate: a change to it
        belongs to that gate."""
        patterns = _triage_patterns(CI_WORKFLOW)
        assert _matches("tools/audit/pyproject.toml", patterns["py"])
        assert _matches("tools/audit/uv.lock", patterns["py"])
