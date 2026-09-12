"""Skill auto-organization: find repeated tool call sequences and propose
saving them as skills (L1 with confirmation).

Responsibilities:
- detect(): find repeated consecutive tool-call sequences in episodic memory
- propose_and_save(): draft a skill file from a repeated flow and write it only
  after user confirmation (L1); flows already saved are not proposed again
- maybe_propose(): cadence trigger - every N new tool episodes (hot-read
  setting, 0 = off) returns the proposal coroutine for the caller to schedule
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Awaitable
from pathlib import Path

from agent.contracts import ConfirmFn, SettingsReader
from agent.memory.episodic import EpisodicMemory

_TEMPLATE = "# {name}\n\nAuto-organized from a repeated flow (occurred {count} times).\n\n## Steps\n{steps}\n"


class SkillOrganizer:
    def __init__(
        self,
        episodic: EpisodicMemory,
        skills_dir: str | Path,
        *,
        confirm: ConfirmFn | None = None,
        settings: SettingsReader | None = None,
    ) -> None:
        self._episodic = episodic
        self._dir = Path(skills_dir)
        self._confirm = confirm
        self._settings = settings
        self._checked_at = 0  # tool-episode count at the last cadence check

    def detect(self, *, min_count: int = 3, seq_len: int = 2) -> list[dict]:
        """Find repeated consecutive sequences in the episodic memory's tool call stream."""
        entries = self._episodic.recent(limit=500, kind="tool")
        entries.reverse()  # chronological order
        by_run: dict[str, list[str]] = {}
        for e in entries:
            by_run.setdefault(e["run_id"] or "_", []).append(e["summary"])
        grams: Counter[tuple[str, ...]] = Counter()
        for names in by_run.values():
            for i in range(len(names) - seq_len + 1):
                grams[tuple(names[i : i + seq_len])] += 1
        return [
            {"sequence": list(seq), "count": n} for seq, n in grams.most_common() if n >= min_count
        ]

    def maybe_propose(self) -> Awaitable[list[Path]] | None:
        """Cadence: once every `agent.skills.organize_every` new tool episodes
        (0 = off). Returns the proposal coroutine on trigger turns so the
        caller schedules it in the background, None otherwise."""
        if self._settings is None:
            return None
        try:
            every = int(self._settings.get("agent.skills.organize_every") or 0)
        except (TypeError, ValueError):
            return None
        if every <= 0:
            return None
        total = self._episodic.count(kind="tool")
        if total - self._checked_at < every:
            return None
        self._checked_at = total
        return self.propose_and_save()

    async def propose_and_save(self, *, min_count: int = 3, seq_len: int = 2) -> list[Path]:
        """For each repeated pattern: ask the user at L1 (when a confirmation channel exists)
        and write a SKILL.md draft on approval. Already-saved flows are skipped."""
        saved: list[Path] = []
        for hit in self.detect(min_count=min_count, seq_len=seq_len):
            name = "auto-" + "-".join(hit["sequence"])[:40]
            target = self._dir / name
            if (target / "SKILL.md").exists():
                continue
            if self._confirm is not None:
                ok = await self._confirm(
                    f"Found a repeated flow {' -> '.join(hit['sequence'])} (occurred {hit['count']} times). "
                    "Save it as a skill?"
                )
                if not ok:
                    continue
            target.mkdir(parents=True, exist_ok=True)
            steps = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(hit["sequence"]))
            (target / "SKILL.md").write_text(
                _TEMPLATE.format(name=name, count=hit["count"], steps=steps),
                encoding="utf-8",
            )
            saved.append(target / "SKILL.md")
        return saved
