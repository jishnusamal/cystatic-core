"""
Propagation Engine — deterministic layer that builds impact trees.

Given a causal graph and a set of changed symbols, computes:
  "if X changes → what downstream nodes are impacted and with what confidence?"

This is the core product backbone for blast radius computation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core_engine.causal_graph import CausalGraph, CausalEdge, CausalNode


@dataclass
class ImpactNode:
    """A single node in the impact tree."""
    symbol: str
    confidence: float  # propagated confidence (0.0 - 1.0)
    hop_distance: int  # how many hops from the root change
    incoming_edges: list[CausalEdge] = field(default_factory=list)
    is_direct_change: bool = False
    impacted_systems: list[str] = field(default_factory=list)
    node_type: str = "symbol"  # From CausalNode: "symbol" | "endpoint" | "service" | "database" | "queue"
    evidence_location: str = ""  # Grounding evidence from the edge that produced this node
    evidence_snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "confidence": round(self.confidence, 3),
            "hop_distance": self.hop_distance,
            "is_direct_change": self.is_direct_change,
            "impacted_systems": self.impacted_systems,
            "node_type": self.node_type,
            "evidence_location": self.evidence_location,
            "evidence_snippet": self.evidence_snippet,
            "incoming_edges": [
                {
                    "from": e.from_symbol,
                    "type": e.edge_type,
                    "confidence": e.confidence,
                    "evidence_type": e.evidence_type,
                    "evidence_location": e.evidence_location,
                    "evidence_snippet": e.evidence_snippet,
                }
                for e in self.incoming_edges
            ],
        }


@dataclass
class ImpactTree:
    """The complete impact tree for a set of changed symbols."""
    roots: list[ImpactNode] = field(default_factory=list)
    all_nodes: dict[str, ImpactNode] = field(default_factory=dict)

    def get_impacted_symbols(self, min_confidence: float = 0.1) -> list[str]:
        """Get all impacted symbols above a confidence threshold."""
        return [
            n.symbol for n in self.all_nodes.values()
            if n.confidence >= min_confidence and not n.is_direct_change
        ]

    def get_impacted_systems(self) -> list[str]:
        """Get all unique impacted systems."""
        systems: set[str] = set()
        for node in self.all_nodes.values():
            systems.update(node.impacted_systems)
        return sorted(systems)

    def get_impacted_by_type(self, node_type: str) -> list[str]:
        """Get all impacted nodes of a specific type (service, database, endpoint, queue)."""
        return [
            n.symbol for n in self.all_nodes.values()
            if n.node_type == node_type and not n.is_direct_change
        ]

    def get_max_confidence(self) -> float:
        """Get the maximum confidence across all impact nodes."""
        if not self.all_nodes:
            return 0.0
        return max(n.confidence for n in self.all_nodes.values())

    def get_blast_radius(self) -> dict[str, Any]:
        """Get a summary of the blast radius."""
        impacted = self.get_impacted_symbols()
        systems = self.get_impacted_systems()
        impacted_services = self.get_impacted_by_type("service")
        impacted_endpoints = self.get_impacted_by_type("endpoint")
        impacted_databases = self.get_impacted_by_type("database")
        impacted_queues = self.get_impacted_by_type("queue")
        return {
            "total_nodes": len(self.all_nodes),
            "direct_changes": len([n for n in self.all_nodes.values() if n.is_direct_change]),
            "impacted_downstream": len(impacted),
            "impacted_symbols": impacted[:20],  # cap for readability
            "impacted_systems": systems,
            "impacted_services": impacted_services,
            "impacted_endpoints": impacted_endpoints,
            "impacted_databases": impacted_databases,
            "impacted_queues": impacted_queues,
            "max_confidence": self.get_max_confidence(),
            "avg_confidence": round(
                sum(n.confidence for n in self.all_nodes.values()) / max(len(self.all_nodes), 1), 3
            ),
        }


class PropagationEngine:
    """
    Builds an impact tree from a causal graph and a set of changed symbols.

    Strategy:
    1. Start from directly changed symbols (roots)
    2. Traverse downstream through the causal graph
    3. Propagate confidence: confidence_hops = confidence_parent * edge.confidence
    4. Aggregate repeated paths by taking max confidence
    """

    # System mapping from symbols to system names
    SYSTEM_MAP: dict[str, list[str]] = {
        "checkout": ["Checkout"],
        "payment": ["Payment"],
        "pay": ["Payment"],
        "charge": ["Payment"],
        "invoice": ["Invoice"],
        "tax": ["Tax"],
        "order": ["Order"],
        "auth": ["Authentication"],
        "authenticate": ["Authentication"],
        "login": ["Authentication"],
        "subscription": ["Subscription"],
        "billing": ["Billing"],
        "discount": ["Discount"],
        "coupon": ["Discount"],
        "shipping": ["Shipping"],
        "fulfillment": ["Fulfillment"],
        "notification": ["Notification"],
        "email": ["Notification"],
        "webhook": ["Webhook"],
        "cache": ["Caching"],
        "redis": ["Caching"],
    }

    def build_impact_tree(
        self,
        causal_graph: CausalGraph,
        directly_changed: list[str],
        max_hops: int = 5,
        confidence_threshold: float = 0.05,
    ) -> ImpactTree:
        """
        Build impact tree from causal graph and changed symbols.

        Args:
            causal_graph: The system causal graph
            directly_changed: Symbols that were directly modified
            max_hops: Maximum propagation depth
            confidence_threshold: Minimum confidence to include a node
        """
        tree = ImpactTree()

        # Initialize root nodes from directly changed symbols
        for symbol in directly_changed:
            root = ImpactNode(
                symbol=symbol,
                confidence=1.0,
                hop_distance=0,
                is_direct_change=True,
                impacted_systems=self._infer_systems(symbol),
            )
            tree.roots.append(root)
            tree.all_nodes[symbol] = root

        # Traverse downstream
        for symbol in directly_changed:
            self._traverse_downstream(
                graph=causal_graph,
                current_symbol=symbol,
                current_confidence=1.0,
                hops=0,
                max_hops=max_hops,
                confidence_threshold=confidence_threshold,
                tree=tree,
                visited=set(),
            )

        return tree

    def _traverse_downstream(
        self,
        graph: CausalGraph,
        current_symbol: str,
        current_confidence: float,
        hops: int,
        max_hops: int,
        confidence_threshold: float,
        tree: ImpactTree,
        visited: set[tuple[str, str]],
    ) -> None:
        """Recursively traverse downstream through the causal graph."""
        if hops >= max_hops:
            return

        for edge in graph.get_outgoing(current_symbol):
            edge_key = (current_symbol, edge.to_symbol)
            if edge_key in visited:
                continue
            visited.add(edge_key)

            propagated_confidence = current_confidence * edge.confidence

            if propagated_confidence < confidence_threshold:
                continue

            # Update or create node
            if edge.to_symbol not in tree.all_nodes:
                new_node = ImpactNode(
                    symbol=edge.to_symbol,
                    confidence=propagated_confidence,
                    hop_distance=hops + 1,
                    incoming_edges=[edge],
                    impacted_systems=self._infer_systems(edge.to_symbol),
                )
                tree.all_nodes[edge.to_symbol] = new_node
            else:
                existing = tree.all_nodes[edge.to_symbol]
                if propagated_confidence > existing.confidence:
                    existing.confidence = propagated_confidence
                    existing.hop_distance = min(existing.hop_distance, hops + 1)
                if edge not in existing.incoming_edges:
                    existing.incoming_edges.append(edge)
                propagated_confidence = existing.confidence

            self._traverse_downstream(
                graph=graph,
                current_symbol=edge.to_symbol,
                current_confidence=propagated_confidence,
                hops=hops + 1,
                max_hops=max_hops,
                confidence_threshold=confidence_threshold,
                tree=tree,
                visited=visited,
            )

    def _infer_systems(self, symbol: str) -> list[str]:
        """Infer what systems a symbol belongs to based on naming conventions."""
        symbol_lower = symbol.lower()
        systems: set[str] = set()

        for pattern, sys_names in self.SYSTEM_MAP.items():
            if pattern in symbol_lower:
                for sys_name in sys_names:
                    systems.add(sys_name)

        if not systems:
            systems.add("Core")

        return sorted(systems)

    def rank_impact_paths(
        self,
        tree: ImpactTree,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Rank the most impactful propagation paths from root to leaf.

        Builds paths by forward-traversing from each root through
        the impact tree's node edges.

        Returns sorted list of paths with confidence scores.
        """
        paths: list[dict[str, Any]] = []

        for root in tree.roots:
            # DFS from each root to find all downstream paths
            stack: list[tuple[str, list[str], list[str], int]] = [
                (root.symbol, [root.symbol], [], 0)
            ]
            visited_local: set[str] = set()

            while stack:
                current_symbol, current_path, current_edges, hops = stack.pop()

                # Find downstream nodes via their incoming edges
                current_node = tree.all_nodes.get(current_symbol)
                if not current_node:
                    continue

                # Find children: nodes whose incoming edge from_symbol == current_symbol
                children: list[tuple[str, CausalEdge]] = []
                for sym, node in tree.all_nodes.items():
                    if node.is_direct_change and sym != current_symbol:
                        continue
                    for edge in node.incoming_edges:
                        if edge.from_symbol == current_symbol and sym not in current_path:
                            children.append((sym, edge))
                            break

                if children:
                    for next_sym, edge in children:
                        next_node = tree.all_nodes.get(next_sym)
                        if not next_node or next_sym in current_path:
                            continue
                        new_path = current_path + [next_sym]
                        new_edges = current_edges + [edge.edge_type]
                        new_hops = hops + 1

                        if new_hops >= 5:
                            # Path endpoint at max hops
                            paths.append({
                                "path": new_path,
                                "edges": new_edges,
                                "leaf_symbol": next_sym,
                                "confidence": next_node.confidence,
                                "hop_distance": new_hops,
                                "impacted_systems": next_node.impacted_systems,
                            })
                            continue

                        stack.append((next_sym, new_path, new_edges, new_hops))
                else:
                    # Leaf node (no further downstream children)
                    if current_symbol != root.symbol:
                        paths.append({
                            "path": current_path,
                            "edges": current_edges,
                            "leaf_symbol": current_symbol,
                            "confidence": current_node.confidence,
                            "hop_distance": hops,
                            "impacted_systems": current_node.impacted_systems,
                        })

        # Sort by confidence (higher first), then by hop distance (shorter first)
        paths.sort(key=lambda p: (-p["confidence"], p["hop_distance"]))
        # Deduplicate paths with identical symbol sequences
        seen_paths: set[str] = set()
        unique_paths: list[dict[str, Any]] = []
        for p in paths:
            key = "->".join(p["path"])
            if key not in seen_paths:
                seen_paths.add(key)
                unique_paths.append(p)

        return unique_paths[:top_k]


def build_impact_tree(
    causal_graph: CausalGraph,
    directly_changed: list[str],
    max_hops: int = 5,
) -> ImpactTree:
    """Convenience function for building impact tree."""
    return PropagationEngine().build_impact_tree(
        causal_graph=causal_graph,
        directly_changed=directly_changed,
        max_hops=max_hops,
    )