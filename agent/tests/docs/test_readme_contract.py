"""README contract audit (T-22.8, dsh-inspired): every enumerated package
README carries the four contract sections plus Known Limitations and
Deferred Work. Pure-mechanism packages are exempt from Model Experience via
the frozen MODEL_AGNOSTIC list; missing READMEs must join an exemption list
with a reason or the package gets a README.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import agent

SECTIONS = ("## Purpose", "## Configuration", "## Extension Points", "## Model Experience")
EXTRA_SECTIONS = ("## Known Limitations", "## Deferred Work")

REPO = Path(__file__).resolve().parents[3]
AGENT_SRC = Path(agent.__file__).parent

#: Domain packages (README + full four-section contract + extras)
DOMAIN_READMES = [
    "packages/notes/README.md",
    "packages/sources/README.md",
    "packages/graph/README.md",
    "packages/llm/README.md",
    "packages/settings/README.md",
    "packages/office/README.md",
    "packages/browser/README.md",
    "packages/code_exec/README.md",
    "packages/host/README.md",
    "packages/gateway/README.md",
    "packages/platform/webguard/README.md",
    "agent/README.md",
]

#: Pure-mechanism packages: "model-agnostic" exemption from Model Experience
#: (documented here, in one place).
MODEL_AGNOSTIC = {
    "packages/platform/contracts/README.md",
    "packages/platform/eventbus/README.md",
    "packages/platform/actor/README.md",
    "packages/platform/settings/README.md",
    "packages/platform/health/README.md",
    "packages/platform/secrets/README.md",
    "packages/platform/capability/README.md",
    "packages/_template/README.md",
}

#: Mechanism subpackages of the agent (model-agnostic too).
AGENT_MECHANISM_READMES = [
    f"agent/src/agent/{d}/README.md" for d in ("runtime", "memory", "policy", "master")
]

ALL = DOMAIN_READMES + sorted(MODEL_AGNOSTIC) + AGENT_MECHANISM_READMES


class TestReadmeContract:
    @pytest.mark.parametrize("rel", ALL)
    def test_readme_exists(self, rel: str) -> None:
        assert (REPO / rel).is_file(), f"missing README: {rel}"

    @pytest.mark.parametrize("rel", ALL)
    def test_four_sections_present(self, rel: str) -> None:
        text = (REPO / rel).read_text(encoding="utf-8")
        missing = [s for s in SECTIONS if s not in text]
        if rel in MODEL_AGNOSTIC:
            missing = [m for m in missing if m != "## Model Experience"]
        assert missing == [], f"{rel}: README missing sections {missing}"

    @pytest.mark.parametrize("rel", DOMAIN_READMES + AGENT_MECHANISM_READMES)
    def test_limitations_and_deferred(self, rel: str) -> None:
        text = (REPO / rel).read_text(encoding="utf-8")
        missing = [s for s in EXTRA_SECTIONS if s not in text]
        assert missing == [], f"{rel}: missing {missing}"
