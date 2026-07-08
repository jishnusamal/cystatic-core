"""KnowledgeModel - the central data structure of the Core Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass(frozen=True)
class KnowledgeModel:
    """Immutable knowledge model representing analyzed software system.
    
    This is the central data structure that accumulates facts
    from all compiler passes. Each pass enriches this model.
    
    The model is immutable - passes return new instances with added facts.
    """
    
    # Core identifiers
    graph_id: str
    commit_hash: str
    
    # Execution structures
    execution_units: List[str] = field(default_factory=list)  # ExecutionUnit IDs
    
    # Interaction structures
    interaction_clusters: List[str] = field(default_factory=list)  # InteractionCluster IDs
    
    # Propagation analysis
    propagation_paths: List[str] = field(default_factory=list)  # PropagationPath IDs
    
    # Coverage information
    coverage: Optional[str] = None  # Coverage ID
    
    # Evidence collected
    evidence: List[str] = field(default_factory=list)  # Evidence IDs
    
    # Signals detected
    signals: List[str] = field(default_factory=list)  # Signal IDs
    
    # External surface changes
    api_changes: List[str] = field(default_factory=list)
    event_changes: List[str] = field(default_factory=list)
    schema_changes: List[str] = field(default_factory=list)
    migration_changes: List[str] = field(default_factory=list)
    external_service_calls: List[str] = field(default_factory=list)
    queue_changes: List[str] = field(default_factory=list)
    cache_changes: List[str] = field(default_factory=list)
    
    # Metadata
    pass_metadata: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    diagnostics: List[str] = field(default_factory=list)
    
    def with_execution_unit(self, unit_id: str) -> KnowledgeModel:
        """Return a new model with an added execution unit."""
        return KnowledgeModel(
            graph_id=self.graph_id,
            commit_hash=self.commit_hash,
            execution_units=self.execution_units + [unit_id],
            interaction_clusters=self.interaction_clusters,
            propagation_paths=self.propagation_paths,
            coverage=self.coverage,
            evidence=self.evidence,
            signals=self.signals,
            api_changes=self.api_changes,
            event_changes=self.event_changes,
            schema_changes=self.schema_changes,
            migration_changes=self.migration_changes,
            external_service_calls=self.external_service_calls,
            queue_changes=self.queue_changes,
            cache_changes=self.cache_changes,
            pass_metadata=self.pass_metadata,
            diagnostics=self.diagnostics,
        )
    
    def with_signal(self, signal_id: str) -> KnowledgeModel:
        """Return a new model with an added signal."""
        return KnowledgeModel(
            graph_id=self.graph_id,
            commit_hash=self.commit_hash,
            execution_units=self.execution_units,
            interaction_clusters=self.interaction_clusters,
            propagation_paths=self.propagation_paths,
            coverage=self.coverage,
            evidence=self.evidence,
            signals=self.signals + [signal_id],
            api_changes=self.api_changes,
            event_changes=self.event_changes,
            schema_changes=self.schema_changes,
            migration_changes=self.migration_changes,
            external_service_calls=self.external_service_calls,
            queue_changes=self.queue_changes,
            cache_changes=self.cache_changes,
            pass_metadata=self.pass_metadata,
            diagnostics=self.diagnostics,
        )
    
    def with_diagnostic(self, message: str) -> KnowledgeModel:
        """Return a new model with an added diagnostic."""
        return KnowledgeModel(
            graph_id=self.graph_id,
            commit_hash=self.commit_hash,
            execution_units=self.execution_units,
            interaction_clusters=self.interaction_clusters,
            propagation_paths=self.propagation_paths,
            coverage=self.coverage,
            evidence=self.evidence,
            signals=self.signals,
            api_changes=self.api_changes,
            event_changes=self.event_changes,
            schema_changes=self.schema_changes,
            migration_changes=self.migration_changes,
            external_service_calls=self.external_service_calls,
            queue_changes=self.queue_changes,
            cache_changes=self.cache_changes,
            pass_metadata=self.pass_metadata,
            diagnostics=self.diagnostics + [message],
        )
    
    def with_evidence(self, evidence_id: str) -> KnowledgeModel:
        """Return a new model with an added evidence."""
        return KnowledgeModel(
            graph_id=self.graph_id,
            commit_hash=self.commit_hash,
            execution_units=self.execution_units,
            interaction_clusters=self.interaction_clusters,
            propagation_paths=self.propagation_paths,
            coverage=self.coverage,
            evidence=self.evidence + [evidence_id],
            signals=self.signals,
            api_changes=self.api_changes,
            event_changes=self.event_changes,
            schema_changes=self.schema_changes,
            migration_changes=self.migration_changes,
            external_service_calls=self.external_service_calls,
            queue_changes=self.queue_changes,
            cache_changes=self.cache_changes,
            pass_metadata=self.pass_metadata,
            diagnostics=self.diagnostics,
        )
    
    def with_coverage(self, coverage_id: str) -> KnowledgeModel:
        """Return a new model with coverage set."""
        return KnowledgeModel(
            graph_id=self.graph_id,
            commit_hash=self.commit_hash,
            execution_units=self.execution_units,
            interaction_clusters=self.interaction_clusters,
            propagation_paths=self.propagation_paths,
            coverage=coverage_id,
            evidence=self.evidence,
            signals=self.signals,
            api_changes=self.api_changes,
            event_changes=self.event_changes,
            schema_changes=self.schema_changes,
            migration_changes=self.migration_changes,
            external_service_calls=self.external_service_calls,
            queue_changes=self.queue_changes,
            cache_changes=self.cache_changes,
            pass_metadata=self.pass_metadata,
            diagnostics=self.diagnostics,
        )
    
    @classmethod
    def empty(cls, graph_id: str, commit_hash: str) -> KnowledgeModel:
        """Create an empty knowledge model."""
        return cls(graph_id=graph_id, commit_hash=commit_hash)
