"""Regression coverage for the uv dependency policy check.

The check scans every committed lockfile, not only the root one: the audit
tool lives in a project of its own, and a ban must hold for its lockfile
too. Nothing in the runtime suite observed that, so a change that dropped
the non-root lockfiles from the scan - or that stopped reading the git
index - would keep the suite green and let a banned package through. The
multi-lockfile path is asserted here instead.
"""

import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/ci/check_uv_deps_policy.py"

# A nested project of its own, like the audit tool of this repository.
NESTED_LOCKFILE = "tools/audit/uv.lock"


def _git(repo: Path, hooks: Path, *arguments: str) -> str:
    """The output of a git command run in the repository at `repo`.

    The commit hooks of the machine are left out (`core.hooksPath`): the
    repository of a test is a throwaway one, and the hooks of the checkout
    it was created for have nothing to say about it.
    """
    completed = subprocess.run(
        ["git", "-C", str(repo), "-c", f"core.hooksPath={hooks}", *arguments],
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout


def _commit(repo: Path, hooks: Path, message: str) -> None:
    """Commit the staged files with a fixed identity.

    The identity is passed on the command line, so the machine that runs
    the test needs no git configuration of its own.
    """
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            f"core.hooksPath={hooks}",
            "-c",
            "user.name=Dependency Policy Test",
            "-c",
            "user.email=deps-policy@example.invalid",
            "commit",
            "-m",
            message,
        ],
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _lockfile(packages: dict[str, str]) -> str:
    """A uv lockfile text that holds the given packages.

    The check reads the [[package]] blocks, so the name and the version of
    a block are all a lockfile needs to carry here.
    """
    blocks = [
        f'[[package]]\nname = "{name}"\nversion = "{version}"\n'
        for name, version in packages.items()
    ]
    return "\n".join(blocks)


def _repository(
    tmp_path: Path,
    root_packages: dict[str, str],
    nested_packages: dict[str, str],
) -> Path:
    """A git repository with a committed root and a committed nested lockfile.

    Both lockfiles are committed, so the check finds both of them in the
    git index.
    """
    repo = tmp_path / "repository"
    repo.mkdir()
    hooks = tmp_path / "no-hooks"
    hooks.mkdir()
    _git(repo, hooks, "init")
    (repo / "uv.lock").write_text(_lockfile(root_packages), encoding="utf-8")
    nested = repo / NESTED_LOCKFILE
    nested.parent.mkdir(parents=True)
    nested.write_text(_lockfile(nested_packages), encoding="utf-8")
    _git(repo, hooks, "add", "--", "uv.lock", NESTED_LOCKFILE)
    _commit(repo, hooks, "commit the lockfiles")
    return repo


def _policy(tmp_path: Path, banned: dict[str, str]) -> Path:
    """A dependency policy file that bans the given pip distributions."""
    policy = tmp_path / "dependency-policy.json"
    policy.write_text(json.dumps({"npm": {}, "pip": banned}), encoding="utf-8")
    return policy


def _check_module() -> ModuleType:
    """The dependency policy check, loaded by file path.

    The script lives in `scripts/ci`, which is no importable package, so
    it is loaded the way the CI runs it: as a file.
    """
    spec = importlib.util.spec_from_file_location("check_uv_deps_policy", SCRIPT)
    assert spec is not None, f"the dependency policy script is missing: {SCRIPT}"
    assert spec.loader is not None, f"the dependency policy script is not loadable: {SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _patched_check(
    repo: Path,
    policy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> ModuleType:
    """The dependency policy check, pointed at the given repository and policy."""
    module = _check_module()
    monkeypatch.setattr(module, "ROOT", repo)
    monkeypatch.setattr(module, "POLICY", policy)
    return module


class TestCommittedLockfiles:
    def test_the_nested_lockfile_is_scanned_too(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Both committed lockfiles are found.

        The scan reads the git index, so a lockfile of a nested project
        counts as much as the root lockfile.
        """
        repo = _repository(tmp_path, {"root-package": "1.0.0"}, {"nested-package": "2.0.0"})
        module = _check_module()
        monkeypatch.setattr(module, "ROOT", repo)

        found = module.lockfiles()

        assert set(found) == {repo / "uv.lock", repo / NESTED_LOCKFILE}

    def test_a_ban_in_a_nested_lockfile_fails_the_check(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A banned distribution that only a nested lockfile resolves fails
        the check, and the finding names the lockfile it came from."""
        repo = _repository(tmp_path, {"root-package": "1.0.0"}, {"banned-package": "2.0.0"})
        policy = _policy(tmp_path, {"banned-package": "banned by policy"})
        module = _patched_check(repo, policy, monkeypatch)

        exit_code = module.main()
        output = capsys.readouterr().out

        assert exit_code == 1, output
        assert "banned-package" in output
        assert NESTED_LOCKFILE in output

    def test_a_ban_that_no_lockfile_resolves_passes_the_check(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A ban on a distribution that no committed lockfile resolves does
        not fail the check."""
        repo = _repository(tmp_path, {"root-package": "1.0.0"}, {"nested-package": "2.0.0"})
        policy = _policy(tmp_path, {"absent-package": "banned by policy"})
        module = _patched_check(repo, policy, monkeypatch)

        exit_code = module.main()
        output = capsys.readouterr().out

        assert exit_code == 0, output
        assert "absent-package" not in output
        assert "policy ok" in output
