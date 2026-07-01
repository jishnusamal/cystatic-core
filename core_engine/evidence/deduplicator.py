"""
Evidence Deduplicator — merges evidence items that describe the same underlying fact.

Instead of treating five observations about the same thing as separate evidence,
group them into one cluster with multiple supporting facts.

Example:
    "UserService touches User"
    "UserController calls UserService"
    "update_user modifies User"
    "UserRepository writes User"
    "User endpoint changes User"

All collapse into "Cluster: User Update Flow" with 5 supporting facts.
"""
from __future__ import annotations

from typing import Any

from core_engine.models.impact_evidence import ImpactEvidence
from core_engine.models.enums import EvidenceType


class DeduplicationKey:
    """Represents a canonical key for grouping equivalent evidence."""

    __slots__ = ("business_object", "domain", "flow_label")

    def __init__(
        self,
        business_object: str = "",
        domain: str = "",
        flow_label: str = "",
    ):
        self.business_object = business_object
        self.domain = domain
        self.flow_label = flow_label

    def __hash__(self) -> int:
        return hash((self.business_object, self.domain, self.flow_label))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DeduplicationKey):
            return False
        return (
            self.business_object == other.business_object
            and self.domain == other.domain
            and self.flow_label == other.flow_label
        )


class EvidenceDeduplicator:
    """Deduplicates impact evidence by grouping equivalent items.

    Strategy:
      1. If evidence references a business object, group by that business object.
      2. If evidence references a domain, group by domain + action type.
      3. Otherwise, group by (source_normalized, target_normalized).
      4. Normalize entity identifiers to catch renames/aliases.
    """

    # Evidence types that indicate the same underlying concern
    EQUIVALENCE_GROUPS: dict[str, str] = {
        # All database evidence about the same table
        "writes_table": "database_operation",
        "reads_table": "database_operation",
        "shares_table": "database_operation",
        "shared_database_table": "database_operation",
        # All transaction evidence about the same flow
        "starts_transaction": "transaction_operation",
        "commits_transaction": "transaction_operation",
        "rolls_back_transaction": "transaction_operation",
        "inside_transaction": "transaction_operation",
        "shared_transaction": "transaction_operation",
        # All event evidence about the same event
        "publishes_event": "event_operation",
        "consumes_event": "event_operation",
        "shared_event": "event_operation",
        "shared_event_publication": "event_operation",
        "shared_event_consumption": "event_operation",
        "event_publication_consumption": "event_operation",
        # All cache evidence about the same cache
        "reads_cache": "cache_operation",
        "shared_cache": "cache_operation",
        "cache_dependency": "cache_operation",
    }

    @staticmethod
    def deduplicate(
        evidence_list: list[ImpactEvidence | dict[str, Any]],
        business_objects: list[dict[str, Any]] | None = None,
    ) -> list[list[ImpactEvidence | dict[str, Any]]]:
        """Group equivalent evidence items into clusters.

        Args:
            evidence_list: List of ImpactEvidence objects or dicts.
            business_objects: Business object metadata for context.

        Returns:
            List of evidence groups. Each group is a list of equivalent items.
        """
        # Build business object lookup: symbol/text → (bo_name, domain)
        bo_lookup: dict[str, tuple[str, str]] = {}
        if business_objects:
            for bo in business_objects:
                name = bo.get("name", "") if isinstance(bo, dict) else (bo.name if hasattr(bo, "name") else "")
                domain = bo.get("domain", "") if isinstance(bo, dict) else (bo.domain if hasattr(bo, "domain") else "")
                aliases = bo.get("aliases", []) if isinstance(bo, dict) else (bo.aliases if hasattr(bo, "aliases") else [])
                referenced_by = bo.get("referenced_by", []) if isinstance(bo, dict) else []
                if name:
                    bo_lookup[name.lower()] = (name, domain)
                    for alias in aliases:
                        bo_lookup[alias.lower()] = (name, domain)
                    for ref in referenced_by:
                        if isinstance(ref, str):
                            bo_lookup[ref.lower()] = (name, domain)

        groups: dict[DeduplicationKey, list[ImpactEvidence | dict[str, Any]]] = {}

        for evidence in evidence_list:
            key = EvidenceDeduplicator._compute_key(evidence, bo_lookup)
            if key not in groups:
                groups[key] = []
            groups[key].append(evidence)

        return list(groups.values())

    @staticmethod
    def _compute_key(
        evidence: ImpactEvidence | dict[str, Any],
        bo_lookup: dict[str, tuple[str, str]],
    ) -> DeduplicationKey:
        """Compute a deduplication key for an evidence item."""
        # Extract fields
        if hasattr(evidence, "source"):
            # ImpactEvidence object
            source = evidence.source.id if hasattr(evidence.source, "id") else str(evidence.source)
            target = evidence.target.id if hasattr(evidence.target, "id") else str(evidence.target)
            evidence_type = evidence.evidence_type
            if hasattr(evidence_type, "value"):
                evidence_type = evidence_type.value
            evidence_type = str(evidence_type)
            metadata = evidence.metadata or {}
        else:
            source = evidence.get("source_symbol", "")
            target = evidence.get("target_symbol", "")
            evidence_type = evidence.get("evidence_type", "")
            metadata = evidence.get("metadata", {})

        source_lower = source.lower()
        target_lower = target.lower()

        # Check if source or target maps to a business object
        bo_name = ""
        domain = ""
        for lookup_key, (bname, bdomain) in bo_lookup.items():
            if lookup_key in source_lower or lookup_key in target_lower:
                bo_name = bname
                domain = bdomain
                break

        # Check metadata for business object
        if not bo_name:
            meta_bo = metadata.get("business_object", "")
            if meta_bo:
                bo_name = meta_bo
                domain = metadata.get("domain", "")

        # Determine flow label from evidence type
        flow_label = EvidenceDeduplicator.EQUIVALENCE_GROUPS.get(evidence_type, "")

        # If no flow label, use the evidence type itself
        if not flow_label:
            flow_label = evidence_type

        return DeduplicationKey(
            business_object=bo_name or "",
            domain=domain or "",
            flow_label=flow_label,
        )

    @staticmethod
    def merge_group(
        group: list[ImpactEvidence | dict[str, Any]]
    ) -> dict[str, Any]:
        """Merge a group of equivalent evidence into a single cluster descriptor.

        Args:
            group: List of equivalent evidence items.

        Returns:
            Cluster descriptor dict with merged metadata.
        """
        evidence_types: set[str] = set()
        sources: set[str] = set()
        targets: set[str] = set()
        explanations: list[str] = []
        max_confidence = 0.0
        business_object = ""
        domain = ""

        for evidence in group:
            if hasattr(evidence, "source"):
                evidence_type = evidence.evidence_type
                if hasattr(evidence_type, "value"):
                    evidence_type = evidence_type.value
                evidence_types.add(str(evidence_type))
                src = evidence.source.id if hasattr(evidence.source, "id") else str(evidence.source)
                tgt = evidence.target.id if hasattr(evidence.target, "id") else str(evidence.target)
                sources.add(src)
                targets.add(tgt)
                explanations.append(evidence.explanation)
                max_confidence = max(max_confidence, evidence.confidence)
                meta_bo = evidence.metadata.get("business_object", "")
                if meta_bo:
                    business_object = meta_bo
                    domain = evidence.metadata.get("domain", "")
            else:
                evidence_types.add(evidence.get("evidence_type", ""))
                sources.add(evidence.get("source_symbol", ""))
                targets.add(evidence.get("target_symbol", ""))
                explanations.append(evidence.get("explanation", ""))
                max_confidence = max(max_confidence, evidence.get("confidence", 0.0))
                meta = evidence.get("metadata", {})
                meta_bo = meta.get("business_object", "")
                if meta_bo:
                    business_object = meta_bo
                    domain = meta.get("domain", "")

        return {
            "evidence_types": sorted(evidence_types),
            "sources": sorted(sources),
            "targets": sorted(targets),
            "evidence_count": len(group),
            "max_confidence": max_confidence,
            "explanations": explanations,
            "business_object": business_object,
            "domain": domain,
            "supporting_facts": [
                {
                    "source": src,
                    "target": tgt,
                    "type": etype,
                    "explanation": expl,
                }
                for src, tgt, etype, expl in zip(
                    [s for s in sources for _ in targets],
                    [t for _ in sources for t in targets],
                    sorted(evidence_types),
                    explanations,
                )
            ],
        }