"""Supply-chain policy of the CI workflows and the npm scripts.

The install and audit commands are the supply-chain boundary of this
repository: they decide which package versions run, whether an install
script may execute and whether a download may leave HTTPS. Nothing in the
runtime suite observes them, so a change that dropped one of these guards
would leave the whole suite green. The policy is asserted here instead.
"""

import ast
import json
import re
import shlex
import tomllib
from collections import Counter
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

# A URL in a workflow command, wherever it stands. The host may be a
# bracketed IPv6 literal, which the pattern has to keep in one piece so the
# parsed host is checked like any other; the policy is about the host a
# request reaches, not about the program that fetches it.
URL_PATTERN = re.compile(
    r"https?://(?:\[[0-9A-Fa-f:.]+\][^\s'\"`()<>{},;\\\[\]]*|[^\s'\"`()<>{},;\\\[\]]+)"
)
# The hosts a workflow request may reach.
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
# The npm scripts that run the Python tooling, mapped to the executable
# their `uv run` invocation has to start. Every one of them reaches the
# interpreter through `uv run`, so the locked environment provides the tool
# and its dependencies; naming the executable keeps an echoed command from
# counting as a run.
PYTHON_TOOLING_SCRIPTS = {
    "audit:py": "python",
    "docs:i18n": "python",
    "docs:links": "python",
    "eval": "pytest",
    "eval:update": "python",
    "graph": "python",
    "graph:check": "python",
    "lint:imports": "lint-imports",
    "lint:py": "ruff",
    "test:py": "pytest",
    "typecheck:py": "mypy",
}
# The `uv run` options that consume the following word, so the word is not
# mistaken for the command uv runs.
UV_RUN_VALUE_OPTIONS = frozenset(
    {
        "-p",
        "--directory",
        "--env-file",
        "--extra",
        "--group",
        "--no-group",
        "--only-group",
        "--package",
        "--project",
        "--python",
        "--with",
        "--with-requirements",
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


def _uv_run_commands(command: str) -> list[list[str]]:
    """The argument vectors of the `uv run` invocations of one shell command."""
    return [argv for argv in _uv_commands(command) if argv[1:2] == ["run"]]


def _uv_run_program(argv: list[str]) -> str | None:
    """The executable a `uv run` invocation starts.

    uv runs its first positional argument after the options, so the options
    are walked instead of searching the words: a tool named as an option
    value is not the tool that runs.
    """
    index = 2
    while index < len(argv):
        argument = argv[index]
        if argument.startswith("-"):
            index += 2 if argument in UV_RUN_VALUE_OPTIONS else 1
            continue
        return argument
    return None


def _assert_expected_python_tooling_scripts() -> None:
    """Every expected Python-tooling script runs its tool through `uv run`.

    The scripts are parsed, not searched as text: an echoed command starts
    no tool, so it does not count as a caller. The expected executable is
    checked as well, so a caller that runs something else fails too.
    """
    scripts: dict[str, str] = PACKAGE_JSON["scripts"]
    missing: list[str] = []
    wrong: list[str] = []
    for name, program in PYTHON_TOOLING_SCRIPTS.items():
        programs = [_uv_run_program(argv) for argv in _uv_run_commands(scripts.get(name, ""))]
        if not programs:
            missing.append(name)
        elif program not in programs:
            wrong.append(f"{name}: expected {program}, ran {programs}")
    assert not missing, f"the Python tooling scripts left the locked environment: {sorted(missing)}"
    assert not wrong, f"the Python tooling scripts run the wrong tool: {wrong}"


def _flag_value(argv: list[str], flag: str) -> str | None:
    """The word that follows a flag, or None when the flag is absent."""
    for index, argument in enumerate(argv):
        if argument == flag and index + 1 < len(argv):
            return argv[index + 1]
    return None


def _flag_values(argv: list[str], flag: str) -> list[str]:
    """The words that follow a flag, in the order they appear.

    A flag may be given more than once (pip-audit reads several
    requirement files), so every occurrence counts.
    """
    return [
        argv[index + 1]
        for index, argument in enumerate(argv)
        if argument == flag and index + 1 < len(argv)
    ]


def _pins(requirements: list[str]) -> dict[str, str]:
    """The exact pins of a requirement list, name -> pinned version.

    Requirements without an exact pin are left out; `_exact_pins` asserts
    that none are.
    """
    pins: dict[str, str] = {}
    for requirement in requirements:
        name, separator, version = requirement.partition("==")
        if separator and version:
            pins[name] = version
    return pins


def _exact_pins(requirements: list[str], scope: str) -> dict[str, str]:
    """The exact pins of a requirement list where every entry has to pin."""
    pins = _pins(requirements)
    assert len(pins) == len(requirements), f"not an exact pin in the {scope}: {requirements}"
    return pins


def _requirement_name(requirement: str) -> str:
    """The distribution name of a PEP 508 requirement string."""
    match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", requirement)
    assert match is not None, requirement
    return match.group(0)


def _workspace_build_requirements() -> list[str]:
    """The build requirements every editable workspace member declares."""
    requires: list[str] = []
    for member in APP_PYPROJECT["tool"]["uv"]["workspace"]["members"]:
        manifest = tomllib.loads((ROOT / member / "pyproject.toml").read_text(encoding="utf-8"))
        member_requires = manifest["build-system"]["requires"]
        assert member_requires, member
        requires.extend(member_requires)
    return requires


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
    project = _script_constants(AUDIT_SCRIPT).get("AUDIT_PROJECT")
    assert project is not None, "the audit script no longer names the audit project"
    return (ROOT / project).resolve()


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


def _workflow_urls(workflow: str) -> list[tuple[str, str]]:
    """The URLs a workflow names and the command that names them.

    The policy is about the URL, not the program that fetches it: a URL
    in the code of a Python command leaves the machine just as a URL in a
    curl command does, and a program outside any whitelist is no
    exception. A trailing comment names no request, so it is left out.
    """
    found: list[tuple[str, str]] = []
    for line in workflow.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        command = stripped.split(" #", 1)[0]
        for url in URL_PATTERN.findall(command):
            found.append((stripped, url))
    return found


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
            argv = _argv(command)
            # The install has to be the command that runs, not a word in
            # an echo of it.
            assert argv[:2] == ["npm", "ci"], command
            assert "--ignore-scripts" in argv, command

    def test_playwright_comes_from_the_installed_workspace(self) -> None:
        """The step runs the workspace binary, not a word in an echo of it."""
        commands = _commands(CI_WORKFLOW, "playwright install")
        assert commands, "the workflow no longer installs the browser"
        for command in commands:
            argv = _argv(command)
            assert argv[:2] == ["node_modules/.bin/playwright", "install"], command
            assert "--with-deps" in argv, command
            assert "chromium" in argv, command
        assert not _commands(CI_WORKFLOW, "npx "), "the workflow resolves packages with npx"


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


class TestLockedBuildBackend:
    """The editable workspace members are built on every install, so their
    build backend runs as third-party code. The backend has to be a locked
    dependency, and the build environment has to be constrained to the
    versions the lockfile records."""

    def test_the_build_backend_is_a_pinned_locked_dev_dependency(self) -> None:
        """The backend is a real dependency of this lockfile, so it is
        installed from the lock (and scanned by the audit) like everything
        else."""
        dev_pins = _pins(APP_PYPROJECT["dependency-groups"]["dev"])
        packages = _lock_packages(APP_UV_LOCK)
        for requirement in _workspace_build_requirements():
            name = _requirement_name(requirement)
            assert name in dev_pins, f"the backend is not a pinned dev dependency: {requirement}"
            assert name in packages, f"{name} is not resolved in uv.lock"
            assert packages[name]["version"] == dev_pins[name], (name, packages[name])

    def test_the_build_environment_is_constrained_to_locked_versions(self) -> None:
        """uv resolves the build requirements from the index while building,
        so every one of them is constrained to the exact version the
        lockfile resolves. The lockfile records the constraints, which makes
        `--locked` reject a manifest that drifts from them."""
        pins = _exact_pins(
            APP_PYPROJECT["tool"]["uv"]["build-constraint-dependencies"],
            "build constraints",
        )
        assert pins
        packages = _lock_packages(APP_UV_LOCK)
        for name, version in pins.items():
            assert name in packages, f"{name} is not resolved in uv.lock"
            assert packages[name]["version"] == version, (name, packages[name], version)
        for requirement in _workspace_build_requirements():
            assert _requirement_name(requirement) in pins, (
                f"the build environment is not constrained for {requirement}"
            )
        recorded = APP_UV_LOCK["manifest"].get("build-constraints", [])
        assert {(entry["name"], entry["specifier"]) for entry in recorded} == {
            (name, f"=={version}") for name, version in pins.items()
        }


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
        """The exported sets must be the scanned sets: every export writes
        its own file, and the audit reads each of them exactly once. A
        shared output path would let the second export overwrite the first
        and leave one set unscanned."""
        exports = _uv_invocations(AUDIT_SCRIPT, "export")
        runs = _uv_invocations(AUDIT_SCRIPT, "run")
        assert exports, "the audit script no longer exports the resolution"
        assert runs, "the audit script no longer runs the audit tool"
        written: list[str] = []
        for export in exports:
            path = _flag_value(export, "-o")
            assert path is not None, export
            written.append(path)
        assert len(set(written)) == len(written), f"the exports share one output path: {written}"
        scanned = [value for run in runs for value in _flag_values(run, "-r")]
        assert Counter(scanned) == Counter(written), (scanned, written)

    def test_both_sets_are_scanned_by_one_run(self) -> None:
        """Both sets are scanned by one invocation, and each exported set is
        read exactly once. A second run would audit the sets separately; a
        repeated path would leave one set unscanned."""
        exports = _uv_invocations(AUDIT_SCRIPT, "export")
        runs = _uv_invocations(AUDIT_SCRIPT, "run")
        assert exports, "the audit script no longer exports the resolution"
        assert len(runs) == 1, f"the audit scans in more than one run: {runs}"
        written: list[str] = []
        for export in exports:
            path = _flag_value(export, "-o")
            assert path is not None, export
            written.append(path)
        scanned = _flag_values(runs[0], "-r")
        assert sorted(scanned) == sorted(written), (scanned, written)
        assert len(set(scanned)) == len(scanned), f"the audit reads one set twice: {scanned}"

    def test_the_audit_resolves_nothing_at_run_time(self) -> None:
        """The pins of the lockfiles are the scanned set, so the scan may
        not resolve them again. The exports carry the hashes of the
        lockfile, so the scan needs no resolution to read them."""
        runs = _uv_invocations(AUDIT_SCRIPT, "run")
        assert runs, "the audit script no longer runs the audit tool"
        for argv in runs:
            assert "--disable-pip" in argv, argv
        exports = _uv_invocations(AUDIT_SCRIPT, "export")
        assert exports, "the audit script no longer exports the resolution"
        for export in exports:
            assert "--no-hashes" not in export, export

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
        next to it. Every run has to select the isolated project, so a
        second run cannot leave it."""
        runs = _uv_invocations(AUDIT_SCRIPT, "run")
        assert runs, "the audit script no longer runs the audit tool"
        project = _audit_project()
        assert project != ROOT, project
        constants = _script_constants(AUDIT_SCRIPT)
        for argv in runs:
            selected = _flag_value(argv, "--project")
            assert selected is not None, argv
            assert (ROOT / constants.get(selected, selected)).resolve() == project, argv
        # The audit project is excluded from the workspace, so it keeps its
        # own lockfile instead of sharing the root one.
        assert "tools/audit" in APP_PYPROJECT["tool"]["uv"]["workspace"]["exclude"]

    def test_audit_script_runs_in_the_isolated_project(self) -> None:
        """`npm run audit:py` starts the script in the audit project: uv run
        there never syncs the root project, so the job installs no
        application dependency before the scan starts."""
        runs = _uv_run_commands(PACKAGE_JSON["scripts"]["audit:py"])
        assert runs, "audit:py no longer runs the audit script"
        project = _audit_project()
        constants = _script_constants(AUDIT_SCRIPT)
        for argv in runs:
            selected = _flag_value(argv, "--project")
            assert selected is not None, argv
            assert (ROOT / constants.get(selected, selected)).resolve() == project, argv

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
            # The download has to be the command that runs, not a word in
            # an echo of it.
            assert argv[0] == "curl", command
            assert _flag_value(argv, "--proto") == "=https", command
            assert _flag_value(argv, "--proto-redir") == "=https", command
            assert "--tlsv1.2" in argv, command
            # `--next` starts another transfer and drops the options of
            # the previous one, so a transfer behind it would be
            # unguarded.
            assert "--next" not in argv, command

    def test_workflow_requests_stay_on_the_local_host(self) -> None:
        """Every URL the CI workflow names reaches a local host: the
        release downloads of the security workflow are a separate concern
        (test_release_downloads_pin_https_and_tls)."""
        urls = _workflow_urls(CI_WORKFLOW)
        assert urls, "the workflow no longer names a URL"
        for command, url in urls:
            host = urlparse(url).hostname
            assert host in LOCAL_HOSTS, f"{command} -> {url}"

    def test_ipv6_literal_urls_are_extracted(self) -> None:
        """A bracketed IPv6 literal is a host like any other: the extraction
        has to keep it in one piece, or the host check never sees it."""
        workflow = (
            "run: curl -sf 'https://[2001:4860:4860::1]/health'\n"
            "run: curl -sf 'http://[::1]:8000/health'\n"
        )
        found = _workflow_urls(workflow)
        assert [url for _, url in found] == [
            "https://[2001:4860:4860::1]/health",
            "http://[::1]:8000/health",
        ]
        external, loopback = (urlparse(url).hostname for _, url in found)
        assert external == "2001:4860:4860::1"
        assert external not in LOCAL_HOSTS
        assert loopback in LOCAL_HOSTS


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
