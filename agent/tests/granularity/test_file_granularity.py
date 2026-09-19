"""File-granularity audit: one tool per file under tools/<group>/, one
capability per file under capabilities/<group>/, file name = product name.

This is the only cross-cutting test of the agent package (§4.4 F1-F9). It
locks the shape of both projections so an asymmetry is visible from the
directory listing alone:
- tools/<group>/<name>.py exports exactly `<name>_tool` and constructs one
  AgentTool named <name>;
- capabilities/<group>/<name>.py holds exactly one @capability whose name is
  <name> and a `register(reg, deps)` binder;
- mechanism and aggregation files are enumerated in frozen allowlists with a
  reason each; adding one means editing the list on purpose.
"""

from __future__ import annotations

import ast
from pathlib import Path

import agent

SRC = Path(agent.__file__).parent
TOOLS = SRC / "tools"
CAPS = SRC / "capabilities"

#: Mechanism files under tools/<group>/ (F5): reused by several tools, named
#: after the mechanism, never a product unit themselves.
TOOL_MECHANISMS: dict[str, str] = {
    "workspace/jail.py": "path jail shared by every fs/search tool (inner defense layer)",
    "workspace/workdir.py": "default working-directory layout used by assembly",
    "workspace/todo_store.py": "todo.json persistence + read_plan projection shared by tool and capability",
    "workspace/edit_matchers.py": "fuzzy match chain (uniqueness-guarded degradation ladder) behind edit",
    "workspace/console_decode.py": "UTF-8 / console-codepage (GBK, UTF-16 on NULs) decode of child output shared by bash",
    "workspace/write_journal.py": "content-addressed write backup behind the fs write tools (checkpoint/audit support)",
    "interact/question_broker.py": "ask/answer Future broker behind ask_user and answer_question",
}

#: Aggregation files under capabilities/ (F4): import + register only.
CAP_AGGREGATION = {"deps.py", "registry.py", "__init__.py"}

#: Groups that exist on only one side by design; every other group must
#: exist on both sides (F7 same-name, same-structure).
TOOL_ONLY_GROUPS = {
    "core",
    "net",
}  # core = mechanism layer; net = the agent's hands (no human REST)

#: Capability groups with no agent tool group of the same name (frozen; a new
#: entry means editing this list on purpose).
CAP_ONLY_GROUPS = {
    # The agent reaches settings through the settings__* domain bridge; the
    # agent registry's settings group is the human REST projection of the
    # shared settings store.
    "settings",
    # Approval memory widens the agent's own permission envelope: granting and
    # revoking remembered L2 confirmations is the user's prerogative (parity
    # exception; the agent sees remembered grants by NOT being re-asked).
    "policy",
}


def _tool_files() -> list[Path]:
    return sorted(
        p
        for p in TOOLS.rglob("*.py")
        if p.name != "__init__.py" and p.parent != TOOLS and p.parent.name != "core"
    )


def _cap_files() -> list[Path]:
    return sorted(
        p for p in CAPS.rglob("*.py") if p.name not in CAP_AGGREGATION and p.parent != CAPS
    )


def _top_level_defs(tree: ast.Module) -> list[str]:
    return [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _dunder_all(tree: ast.Module) -> list[str] | None:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            return [ast.literal_eval(e) for e in node.value.elts]  # type: ignore[attr-defined]
    return None


def _agent_tool_names(tree: ast.Module) -> list[str]:
    """Names of the tools a file constructs: direct AgentTool(name=...) calls
    or capability_tool(registry, "<name>", ...) bindings."""
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = getattr(node.func, "id", "")
        if func == "AgentTool":
            for kw in node.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    names.append(str(kw.value.value))
        elif func == "capability_tool" and len(node.args) >= 2:
            second = node.args[1]
            if isinstance(second, ast.Constant):
                names.append(str(second.value))
    return names


def _capability_names(tree: ast.Module) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                if isinstance(deco, ast.Call) and getattr(deco.func, "id", "") == "capability":
                    for kw in deco.keywords:
                        if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                            names.append(str(kw.value.value))
    return names


class TestToolGranularity:
    def test_meta_directory_is_gone(self) -> None:
        assert not (TOOLS / "meta").exists(), "tools/meta was dissolved into concern groups"

    def test_mechanism_allowlist_is_live(self) -> None:
        for rel in TOOL_MECHANISMS:
            assert (TOOLS / rel).is_file(), f"allowlisted mechanism missing: {rel}"

    def test_every_tool_file_exports_exactly_one_same_named_tool(self) -> None:
        for path in _tool_files():
            rel = path.relative_to(TOOLS).as_posix()
            if rel in TOOL_MECHANISMS:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            stem = path.stem
            factory = f"{stem}_tool"
            defs = _top_level_defs(tree)
            assert factory in defs, f"{rel}: expected factory {factory}, found {defs}"
            exported = _dunder_all(tree)
            assert exported == [factory], f"{rel}: __all__ must be [{factory!r}], got {exported}"
            built = _agent_tool_names(tree)
            assert built == [stem], (
                f"{rel}: must construct exactly one AgentTool named {stem!r}, got {built}"
            )

    def test_tool_files_do_not_import_sibling_tools(self) -> None:
        for path in _tool_files():
            rel = path.relative_to(TOOLS).as_posix()
            if rel in TOOL_MECHANISMS:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            group = path.parent.name
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    mod = node.module
                    if mod.startswith(f"agent.tools.{group}."):
                        leaf = mod.rsplit(".", 1)[-1]
                        assert f"{group}/{leaf}.py" in TOOL_MECHANISMS, (
                            f"{rel}: imports sibling tool {mod}; only mechanisms may be shared"
                        )


class TestCapabilityGranularity:
    def test_no_loose_capability_modules(self) -> None:
        loose = sorted(p.name for p in CAPS.glob("*.py") if p.name not in CAP_AGGREGATION)
        assert loose == [], f"capabilities must live in a group directory: {loose}"

    def test_every_capability_file_holds_exactly_one_same_named_capability(self) -> None:
        for path in _cap_files():
            rel = path.relative_to(CAPS).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names = _capability_names(tree)
            assert names == [path.stem], (
                f"{rel}: expected one @capability named {path.stem!r}, got {names}"
            )
            assert "register" in _top_level_defs(tree), f"{rel}: missing register(reg, deps) binder"

    def test_group_inits_and_registry_are_pure_aggregation(self) -> None:
        for path in [CAPS / "registry.py", *CAPS.glob("*/__init__.py")]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                assert not isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With)), (
                    f"{path.relative_to(CAPS).as_posix()}: aggregation files carry no control flow"
                )


class TestTwoSidedStructure:
    def test_groups_exist_on_both_sides(self) -> None:
        tool_groups = {p.name for p in TOOLS.iterdir() if p.is_dir() and p.name != "__pycache__"}
        cap_groups = {p.name for p in CAPS.iterdir() if p.is_dir() and p.name != "__pycache__"}
        assert tool_groups - TOOL_ONLY_GROUPS <= cap_groups, (
            f"tool groups without a capability group: {tool_groups - TOOL_ONLY_GROUPS - cap_groups}"
        )
        assert cap_groups - CAP_ONLY_GROUPS <= tool_groups, (
            f"capability groups without a tool group: {cap_groups - CAP_ONLY_GROUPS - tool_groups}"
        )
