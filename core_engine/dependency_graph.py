"""Directed graph of module/file dependencies."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field


@dataclass
class DependencyGraph:
    """Adjacency list: node -> set of dependents (reverse) or dependencies (forward)."""

    forward: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    def add_edge(self, source: str, target: str) -> None:
        """``source`` depends on ``target``."""
        self.forward[source].add(target)

    def reverse_graph(self) -> dict[str, set[str]]:
        """Nodes that depend on each key (blast radius from a change)."""
        rev: dict[str, set[str]] = defaultdict(set)
        for src, tgts in self.forward.items():
            for t in tgts:
                rev[t].add(src)
        return rev

    def blast_radius(self, changed: str) -> set[str]:
        """All nodes reachable from ``changed`` along reverse edges (who is affected)."""
        rev = self.reverse_graph()
        seen: set[str] = set()
        q: deque[str] = deque([changed])
        while q:
            n = q.popleft()
            if n in seen:
                continue
            seen.add(n)
            for u in rev.get(n, ()):
                if u not in seen:
                    q.append(u)
        seen.discard(changed)
        return seen
