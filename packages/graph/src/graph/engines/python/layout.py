"""3D force-directed layout (split out of store.py: a concern
entirely separate from graph storage).

Replaced by layout_c when the C extension is available; the Python
implementation is only for initial placement of small graphs / demos.
"""

from __future__ import annotations

import math

from .store import Edge, Node


def force_layout_3d(
    nodes: list[Node],
    edges: list[Edge],
    *,
    iterations: int = 40,
) -> None:
    """Simple 3D force-directed layout (Python; replaced by layout_c when the C extension exists).

    Note: full pairwise repulsion is O(n^2); never run multiple iterations on
    large graphs or the indexing pipeline will stall.
    """
    if not nodes:
        return
    n = len(nodes)
    # Initial spherical distribution
    for i, node in enumerate(nodes):
        if node.x == 0 and node.y == 0 and node.z == 0:
            phi = math.acos(1 - 2 * (i + 0.5) / n)
            theta = math.pi * (1 + 5**0.5) * i
            r = 40.0 + min(n, 500) * 0.05
            node.x = r * math.sin(phi) * math.cos(theta)
            node.y = r * math.sin(phi) * math.sin(theta)
            node.z = r * math.cos(phi)
        node.size = 1.0 + min(8.0, math.log1p(node.in_calls) * 1.5)

    # Large graphs or iterations<=0: spherical placement only; leave layout to the frontend
    if iterations <= 0 or n > 500:
        return

    idx = {node.id: i for i, node in enumerate(nodes)}
    for _ in range(iterations):
        fx = [0.0] * n
        fy = [0.0] * n
        fz = [0.0] * n
        # Repulsion
        for i in range(n):
            for j in range(i + 1, n):
                dx = nodes[i].x - nodes[j].x
                dy = nodes[i].y - nodes[j].y
                dz = nodes[i].z - nodes[j].z
                dist2 = dx * dx + dy * dy + dz * dz + 0.01
                dist = math.sqrt(dist2)
                force = 80.0 / dist2
                fx[i] += force * dx / dist
                fy[i] += force * dy / dist
                fz[i] += force * dz / dist
                fx[j] -= force * dx / dist
                fy[j] -= force * dy / dist
                fz[j] -= force * dz / dist
        # Edge springs
        for e in edges:
            i = idx.get(e.source)
            j = idx.get(e.target)
            if i is None or j is None:
                continue
            dx = nodes[j].x - nodes[i].x
            dy = nodes[j].y - nodes[i].y
            dz = nodes[j].z - nodes[i].z
            dist = math.sqrt(dx * dx + dy * dy + dz * dz) + 0.01
            force = (dist - 12.0) * 0.02
            fx[i] += force * dx / dist
            fy[i] += force * dy / dist
            fz[i] += force * dz / dist
            fx[j] -= force * dx / dist
            fy[j] -= force * dy / dist
            fz[j] -= force * dz / dist
        # Centripetal force
        for i, node in enumerate(nodes):
            fx[i] -= node.x * 0.01
            fy[i] -= node.y * 0.01
            fz[i] -= node.z * 0.01
            node.x += max(-2.0, min(2.0, fx[i]))
            node.y += max(-2.0, min(2.0, fy[i]))
            node.z += max(-2.0, min(2.0, fz[i]))
            node.size = 1.0 + min(8.0, math.log1p(node.in_calls) * 1.5)
