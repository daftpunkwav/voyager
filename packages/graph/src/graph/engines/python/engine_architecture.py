"""GraphEngine architecture surface (mixin): package clusters,
entry points, hotspots, layer approximation.
"""

from __future__ import annotations

from typing import Any


class ArchitectureMixin:
    """self is a GraphEngine (uses _store)."""

    def get_architecture(self, project: str, aspects: list[str] | None = None) -> dict[str, Any]:
        store = self._store(project)
        packages: dict[str, int] = {}
        entry_points: list[dict] = []
        hotspots: list[dict] = []
        for n in store.nodes.values():
            pkg = (n.attrs or {}).get("package") or (
                n.file_path.rsplit("/", 1)[0] if n.file_path else "."
            )
            if n.label == "File":
                packages[pkg] = packages.get(pkg, 0) + 1
            if (
                n.label in ("Function", "Method")
                and n.in_calls == 0
                and n.name
                in {
                    "main",
                    "run",
                    "handler",
                    "app",
                    "index",
                }
            ):
                entry_points.append(
                    {"name": n.name, "qualified_name": n.qualified_name, "file": n.file_path}
                )
            if n.in_calls >= 3:
                hotspots.append(
                    {
                        "name": n.name,
                        "qualified_name": n.qualified_name,
                        "in_calls": n.in_calls,
                        "cyclomatic_complexity": n.attrs.get("cyclomatic_complexity"),
                    }
                )
        hotspots.sort(key=lambda x: x["in_calls"], reverse=True)

        # Simplified Leiden: cluster by package
        clusters = [
            {"id": f"c_{i}", "label": pkg, "size": cnt, "algorithm": "package-leiden-approx"}
            for i, (pkg, cnt) in enumerate(sorted(packages.items(), key=lambda x: -x[1])[:50])
        ]

        layers = [
            {"name": "presentation", "hint": "ui/pages/components"},
            {"name": "application", "hint": "services/api"},
            {"name": "domain", "hint": "models/core"},
            {"name": "infrastructure", "hint": "db/clients"},
        ]
        boundaries = [
            {"from": a["name"], "to": b["name"], "rule": "allowed"}
            for a, b in zip(layers, layers[1:])
        ]

        out = {
            "packages": [{"name": k, "file_count": v} for k, v in sorted(packages.items())],
            "entry_points": entry_points[:50],
            "hotspots": hotspots[:50],
            "layers": layers,
            "boundaries": boundaries,
            "clusters": clusters,
        }
        if aspects:
            return {k: out[k] for k in aspects if k in out}
        return out
