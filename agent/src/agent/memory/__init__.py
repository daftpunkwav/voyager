"""Memory system: four memory kinds plus a retrieval query facade (recall,
loaded on demand).

Retention policy: when retention_days > 0, purge cleans up both overdue
episodes and overdue semantic facts; 0 = agent-managed (no automatic
cleanup).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from platform_contracts import ErrorSuffix, ServiceError

from agent.memory.episodic import EpisodicMemory
from agent.memory.matching import score, split_terms
from agent.memory.profile import ProfileMemory
from agent.memory.semantic import SemanticMemory
from agent.memory.vector import EmbeddingUnavailable, vector_hits
from agent.memory.working import WorkingMemory

#: Clearable memory zones (settings page); "all" means everything
_ZONES = ("profile", "episodic", "semantic", "working")


class Memory:
    _STORES = ("profile", "episodic", "semantic")

    def __init__(self, root: str | Path, *, embedder: Any | None = None) -> None:
        # On-disk stores open lazily on first access (see __getattr__): a
        # working-only Memory never touches the disk, and a root the process
        # cannot create only fails when a durable store is actually needed.
        self._root = Path(root)
        self.working = WorkingMemory()
        self._embedder = embedder  # optional vector channel (memory.vector.EmbeddingFn)
        self._vector_note = ""  # last degradation reason ("" = vector channel served)

    def __getattr__(self, name: str) -> Any:
        # Only called when normal lookup fails: materialize the durable store
        # on first use and cache it as an instance attribute.
        if name in self._STORES:
            store = {
                "profile": ProfileMemory,
                "episodic": EpisodicMemory,
                "semantic": SemanticMemory,
            }[name](self._root / f"{name}.db")
            setattr(self, name, store)
            return store
        raise AttributeError(name)

    def _vector_candidates(self) -> list[tuple[str, str, str, dict[str, Any]]]:
        """Recall candidate pool for the vector channel: (source, identity,
        text, payload); capped per source so one zone cannot dominate."""
        cands: list[tuple[str, str, str, dict[str, Any]]] = []
        for key, value in self.profile.all().items():
            cands.append(
                (
                    "profile",
                    f"profile:{key}",
                    f"{key} {value}",
                    {"from": "profile", "key": key, "value": value},
                )
            )
        for e in self.episodic.recent(50):
            cands.append(
                (
                    "episodic",
                    f"episodic:{e.get('id')}",
                    f"{e.get('kind', '')} {e.get('summary', '')}",
                    {"from": "episodic", **e},
                )
            )
        for f in self.semantic.query(limit=50):
            cands.append(
                (
                    "semantic",
                    f"semantic:{f.get('id')}",
                    f"{f.get('subject', '')} {f.get('relation', '')} {f.get('object', '')}",
                    {"from": "semantic", **f},
                )
            )
        return cands

    def recall(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Retrieval-style injection: aggregates profile/episodic/semantic hits
        with the source labeled.

        Lexical channel: profile key/values hit on any token (same multi-word
        accounting as episodic/semantic search); episodic/semantic rank
        internally by hit-term count. Optional vector channel (an injected
        embedder): similarity-ranked candidates from the pooled stores join
        the lexical hits, de-duplicated per item identity.
        """
        terms = split_terms(query)
        hits: list[dict[str, Any]] = []
        profile_scored: list[tuple[int, dict[str, Any]]] = []
        for key, value in self.profile.all().items():
            hay = f"{key} {value}"
            s = score(terms, [hay])
            if s:
                profile_scored.append((s, {"from": "profile", "key": key, "value": value}))
        profile_scored.sort(key=lambda item: -item[0])
        hits += [item for _, item in profile_scored]
        hits += [{"from": "episodic", **e} for e in self.episodic.search(query, limit)]
        hits += [{"from": "semantic", **f} for f in self.semantic.query(keyword=query, limit=limit)]
        cap = max(limit * 2, 8)
        if self._embedder is not None:
            try:
                vhits = vector_hits(query, self._vector_candidates(), self._embedder, limit=cap)
            except EmbeddingUnavailable as exc:
                # Degrade to the lexical hits already collected and remember
                # why, so get_memory can show the vector channel is off
                self._vector_note = str(exc)
                return hits[:cap]
            self._vector_note = ""
            seen = {(h.get("from"), str(h.get("key", h.get("id", "")))) for h in hits}
            for c in vhits:
                identity = c.identity.split(":", 1)[-1]
                if (c.source, identity) in seen:
                    continue  # already surfaced by the lexical channel
                hits.append({**c.payload, "similarity": round(c.similarity, 4)})
        return hits[:cap]

    def vector_status(self) -> dict[str, Any]:
        """Whether recall has a vector channel and, if it last degraded, why."""
        if self._embedder is None:
            return {"enabled": False, "note": "no embedder injected (lexical recall only)"}
        return {"enabled": not self._vector_note, "note": self._vector_note}

    def purge(self, retention_days: int) -> dict[str, int]:
        if retention_days <= 0:
            return {"episodic": 0, "semantic": 0}  # agent-managed retention
        return {
            "episodic": self.episodic.purge(retention_days),
            "semantic": self.semantic.purge(retention_days),
        }

    def clear(self, zone: str) -> dict[str, int]:
        """Clear one memory zone (settings page "view/clear"), returning the
        per-zone deletion counts.

        Unrelated to purge's retention semantics: clear is an explicit wipe,
        purge is lazy day-based cleanup.
        """
        targets: tuple[str, ...]
        if zone == "all":
            targets = _ZONES
        elif zone in _ZONES:
            targets = (zone,)
        else:
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"unknown memory zone: {zone}",
                hint="zone must be profile / episodic / semantic / working / all",
            )
        out: dict[str, int] = {}
        for z in targets:
            if z == "profile":
                out[z] = self.profile.clear()
            elif z == "episodic":
                out[z] = self.episodic.clear()
            elif z == "semantic":
                out[z] = self.semantic.clear()
            else:
                out[z] = len(self.working)  # count before clearing
                self.working.clear()
        return out

    def close(self) -> None:
        for name in self._STORES:
            store = self.__dict__.get(name)
            if store is not None:
                store.close()


__all__ = [
    "EpisodicMemory",
    "Memory",
    "ProfileMemory",
    "SemanticMemory",
    "WorkingMemory",
]
