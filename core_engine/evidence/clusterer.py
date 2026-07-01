"""
Evidence Clusterer — groups evidence around business objects, domains, and flows.

Key design decisions:
  1. Cluster by propagation target, not by evidence type.
     Instead of "DatabaseEvidence", "ServiceEvidence", produce
     "Payment flow", "Order lifecycle", "User authentication".
  2. Everything concerning the same business object becomes one reasoning unit.
  3. Compute cluster scores from individual evidence scores.
"""
from __future__ import annotations

from typing import Any

from core_engine.models.impact_evidence import ImpactEvidence
from core_engine.evidence.scoring import EvidenceScorer


class EvidenceCluster:
    """A semantic cluster of evidence items.

    Attributes:
        cluster_id: Unique identifier for this cluster.
        label: Human-readable label describing the cluster.
        business_object: Business object this cluster revolves around.
        domain: Business domain this cluster belongs to.
        evidence: Underlying evidence items.
        evidence_scores: Per-item evidence scores.
        cluster_score: Aggregated score for this cluster.
        evidence_count: Number of evidence items in this cluster.
        evidence_types: Distinct evidence types in this cluster.
        sources: Distinct source entities.
        targets: Distinct target entities.
        risk_anchor_types: Risk anchors present in this cluster.
    """

    def __init__(
        self,
        cluster_id: str,
        label: str,
        business_object: str = "",
        domain: str = "",
        risk_anchor_types: list[str] | None = None,
    ):
        self.cluster_id = cluster_id
        self.label = label
        self.business_object = business_object
        self.domain = domain
        self.evidence: list[ImpactEvidence | dict[str, Any]] = []
        self.evidence_scores: list[float] = []
        self.cluster_score = 0.0
        self.evidence_count = 0
        self.evidence_types: set[str] = set()
        self.sources: set[str] = set()
        self.targets: set[str] = set()
        self.risk_anchor_types = risk_anchor_types or []

    def add_evidence(
        self,
        evidence: ImpactEvidence | dict[str, Any],
    ) -> None:
        """Add an evidence item to this cluster."""
        self.evidence.append(evidence)

        # Extract type
        if hasattr(evidence, "evidence_type"):
            etype = evidence.evidence_type
            if hasattr(etype, "value"):
                etype = etype.value
            self.evidence_types.add(str(etype))
            confidence = evidence.confidence
            src = evidence.source.id if hasattr(evidence.source, "id") else str(evidence.source)
            tgt = evidence.target.id if hasattr(evidence.target, "id") else str(evidence.target)
        else:
            self.evidence_types.add(evidence.get("evidence_type", "unknown"))
            confidence = evidence.get("confidence", 0.5)
            src = evidence.get("source_symbol", "")
            tgt = evidence.get("target_symbol", "")

        self.sources.add(src)
        self.targets.add(tgt)

        # Score this evidence
        score = EvidenceScorer.score_evidence(
            list(self.evidence_types)[-1],
            confidence=confidence,
            risk_anchor_types=self.risk_anchor_types,
        )
        self.evidence_scores.append(score)
        self.evidence_count = len(self.evidence)

    def finalize(self) -> None:
        """Compute aggregate cluster score after all evidence is added."""
        self.cluster_score = EvidenceScorer.cluster_score(self.evidence_scores)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "cluster_id": self.cluster_id,
            "label": self.label,
            "business_object": self.business_object,
            "domain": self.domain,
            "cluster_score": self.cluster_score,
            "evidence_count": self.evidence_count,
            "evidence_types": sorted(self.evidence_types),
            "sources": sorted(self.sources),
            "targets": sorted(self.targets),
            "risk_anchor_types": self.risk_anchor_types,
        }


class EvidenceClusterer:
    """Groups evidence items into semantic clusters.

    Clustering strategy:
      1. Business object clustering: Group evidence around known business objects
         (User, Payment, Invoice, Order, etc.).
      2. Target-based clustering: Group evidence that shares the same target entity.
      3. Domain clustering: Group evidence within the same business domain.
      4. Flow clustering: Group evidence along common flows (update, create, delete).
      5. Fallback: Single evidence that doesn't fit anywhere — low confidence, likely pruned.
    """

    @staticmethod
    def cluster(
        evidence_groups: list[list[ImpactEvidence | dict[str, Any]]],
        business_objects: list[dict[str, Any]] | None = None,
        risk_anchor_types: list[str] | None = None,
    ) -> list[EvidenceCluster]:
        """Cluster deduplicated evidence groups into semantic clusters.

        Args:
            evidence_groups: List of deduplicated evidence groups.
            business_objects: Business object metadata.
            risk_anchor_types: Risk anchors present in the change.

        Returns:
            List of EvidenceCluster objects, sorted by score descending.
        """
        clusters: list[EvidenceCluster] = []
        cluster_map: dict[str, EvidenceCluster] = {}

        risk_anchor_types = risk_anchor_types or []

        for group in evidence_groups:
            if not group:
                continue

            # Determine cluster label from the group
            label, bo, domain = EvidenceClusterer._determine_cluster_identity(group, business_objects)
            cluster_id = f"cluster:{bo or domain or label}:{len(clusters)}"

            # Check if we already have a cluster for this label
            existing_key = bo or domain or label
            if existing_key and existing_key in cluster_map:
                cluster = cluster_map[existing_key]
            else:
                cluster = EvidenceCluster(
                    cluster_id=cluster_id,
                    label=label,
                    business_object=bo,
                    domain=domain,
                    risk_anchor_types=risk_anchor_types,
                )
                if existing_key:
                    cluster_map[existing_key] = cluster
                clusters.append(cluster)

            # Add all evidence in this group to the cluster
            for evidence in group:
                cluster.add_evidence(evidence)

        # Finalize all clusters
        for cluster in clusters:
            cluster.finalize()

        # Sort by score descending
        clusters.sort(key=lambda c: c.cluster_score, reverse=True)

        return clusters

    @staticmethod
    def _determine_cluster_identity(
        group: list[ImpactEvidence | dict[str, Any]],
        business_objects: list[dict[str, Any]] | None = None,
    ) -> tuple[str, str, str]:
        """Determine the identity of a cluster from its evidence group."""
        bo_name = ""
        domain = ""
        evidence_types: set[str] = set()
        sources: set[str] = set()
        targets: set[str] = set()

        for evidence in group:
            if hasattr(evidence, "source"):
                if hasattr(evidence, "metadata") and evidence.metadata:
                    meta_bo = evidence.metadata.get("business_object", "")
                    if meta_bo:
                        bo_name = meta_bo
                        domain = evidence.metadata.get("domain", "")
                evidence_types.add(str(evidence.evidence_type))
                src = evidence.source.id if hasattr(evidence.source, "id") else str(evidence.source)
                tgt = evidence.target.id if hasattr(evidence.target, "id") else str(evidence.target)
            else:
                metadata = evidence.get("metadata", {})
                meta_bo = metadata.get("business_object", "")
                if meta_bo:
                    bo_name = meta_bo
                    domain = metadata.get("domain", "")
                evidence_types.add(evidence.get("evidence_type", "unknown"))
                src = evidence.get("source_symbol", "")
                tgt = evidence.get("target_symbol", "")

            sources.add(src)
            targets.add(tgt)

        # Check if business_objects param provides context
        if not bo_name and business_objects:
            for bo in business_objects:
                bo_n = bo.get("name", "") if isinstance(bo, dict) else (bo.name if hasattr(bo, "name") else "")
                bo_refs = bo.get("referenced_by", []) if isinstance(bo, dict) else []
                if bo_n:
                    for src in sources:
                        if bo_n.lower() in src.lower():
                            bo_name = bo_n
                            domain = bo.get("domain", "") if isinstance(bo, dict) else (bo.domain if hasattr(bo, "domain") else "")
                            break
                    for ref in bo_refs:
                        if isinstance(ref, str) and (ref.lower() in {s.lower() for s in sources} or ref.lower() in {t.lower() for t in targets}):
                            bo_name = bo_n
                            domain = bo.get("domain", "") if isinstance(bo, dict) else (bo.domain if hasattr(bo, "domain") else "")
                            break

        # Build label
        if bo_name:
            flow = next(iter(evidence_types), "flow")
            label = f"{bo_name} {flow.replace('_', ' ').title()}"
        elif domain:
            flow = next(iter(evidence_types), "flow")
            label = f"{domain.title()} {flow.replace('_', ' ').title()}"
        else:
            # Use source → target as label
            src = next(iter(sources), "unknown")
            tgt = next(iter(targets), "unknown")
            label = f"{src} → {tgt}"

        return label, bo_name, domain