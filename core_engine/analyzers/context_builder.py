"""Context Builder - transforms KnowledgeModel into LLM reasoning package."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from language_adapters.ir.semantic_graph import SemanticGraph

from core_engine.models.compiler_pass import CompilerPass, PassMetadata, PassResult
from core_engine.models.knowledge_model import KnowledgeModel
from core_engine.models.review_context import ReviewContext


class ContextBuilder(CompilerPass):
    """Transforms the KnowledgeModel into an LLM reasoning package.
    
    Produces ReviewContext containing:
    - Changed execution units
    - Interaction clusters
    - Propagation paths
    - Evidence
    - Signals
    - Coverage
    - Statistics
    
    No conclusions - those are left to the LLM.
    """
    
    metadata = PassMetadata(
        name="context_builder",
        version="1.0.0",
        description="Transforms KnowledgeModel into LLM reasoning package",
        produces=["review_context"],
        consumes=[
            "execution_units",
            "interaction_clusters",
            "propagation_paths",
            "coverage",
            "evidence",
            "signals",
        ],
    )
    
    def execute(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> PassResult:
        """Execute the context building.
        
        Args:
            graph: The semantic graph
            model: The current knowledge model
            
        Returns:
            PassResult with context building results
        """
        diagnostics = []
        
        # Build statistics
        statistics = self._build_statistics(graph, model)
        
        # Build raw facts for LLM
        raw_facts = self._build_raw_facts(graph, model)
        
        # Create review context
        context = ReviewContext(
            context_id=f"context_{model.graph_id}",
            graph_id=model.graph_id,
            commit_hash=model.commit_hash,
            changed_execution_units=model.execution_units,
            interaction_clusters=model.interaction_clusters,
            propagation_paths=model.propagation_paths,
            evidence=model.evidence,
            signals=model.signals,
            coverage=model.coverage,
            statistics=statistics,
            raw_facts=raw_facts,
        )
        
        # Store context in pass_metadata
        updated_model = KnowledgeModel(
            graph_id=model.graph_id,
            commit_hash=model.commit_hash,
            execution_units=model.execution_units,
            interaction_clusters=model.interaction_clusters,
            propagation_paths=model.propagation_paths,
            coverage=model.coverage,
            evidence=model.evidence,
            signals=model.signals,
            api_changes=model.api_changes,
            event_changes=model.event_changes,
            schema_changes=model.schema_changes,
            migration_changes=model.migration_changes,
            external_service_calls=model.external_service_calls,
            queue_changes=model.queue_changes,
            cache_changes=model.cache_changes,
            pass_metadata={**model.pass_metadata, "context_builder": {
                "context_id": context.context_id,
                "statistics": statistics,
            }},
            diagnostics=model.diagnostics,
        )
        
        diagnostics.append(
            f"Built review context with {len(raw_facts)} raw facts"
        )
        
        return PassResult(
            pass_name=self.metadata.name,
            success=True,
            diagnostics=diagnostics,
            metadata={
                "context_id": context.context_id,
                "raw_facts_count": len(raw_facts),
                "statistics": statistics,
            },
        ), updated_model
    
    def _build_statistics(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> Dict[str, Any]:
        """Build statistics about the graph and model."""
        return {
            "total_nodes": len(graph.nodes),
            "total_edges": len(graph.edges),
            "changed_nodes": len([
                n for n in graph.nodes.values()
                if n.change_type in ("added", "modified", "removed")
            ]),
            "execution_units_count": len(model.execution_units),
            "interaction_clusters_count": len(model.interaction_clusters),
            "propagation_paths_count": len(model.propagation_paths),
            "evidence_count": len(model.evidence),
            "signals_count": len(model.signals),
            "api_changes_count": len(model.api_changes),
            "event_changes_count": len(model.event_changes),
            "schema_changes_count": len(model.schema_changes),
            "migration_changes_count": len(model.migration_changes),
            "external_service_calls_count": len(model.external_service_calls),
            "queue_changes_count": len(model.queue_changes),
            "cache_changes_count": len(model.cache_changes),
        }
    
    def _build_raw_facts(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> List[Dict[str, Any]]:
        """Build raw facts for LLM to analyze."""
        facts = []
        
        # Add execution unit facts
        for unit_id in model.execution_units:
            facts.append({
                "type": "execution_unit",
                "id": unit_id,
            })
        
        # Add interaction cluster facts
        for cluster_id in model.interaction_clusters:
            facts.append({
                "type": "interaction_cluster",
                "id": cluster_id,
            })
        
        # Add propagation path facts
        for path_id in model.propagation_paths:
            facts.append({
                "type": "propagation_path",
                "id": path_id,
            })
        
        # Add evidence facts
        for evidence_id in model.evidence:
            facts.append({
                "type": "evidence",
                "id": evidence_id,
            })
        
        # Add signal facts
        for signal_id in model.signals:
            facts.append({
                "type": "signal",
                "id": signal_id,
            })
        
        # Add surface change facts
        for api_id in model.api_changes:
            facts.append({
                "type": "api_change",
                "id": api_id,
            })
        
        for event_id in model.event_changes:
            facts.append({
                "type": "event_change",
                "id": event_id,
            })
        
        for schema_id in model.schema_changes:
            facts.append({
                "type": "schema_change",
                "id": schema_id,
            })
        
        for migration_id in model.migration_changes:
            facts.append({
                "type": "migration_change",
                "id": migration_id,
            })
        
        for ext_id in model.external_service_calls:
            facts.append({
                "type": "external_service_call",
                "id": ext_id,
            })
        
        for queue_id in model.queue_changes:
            facts.append({
                "type": "queue_change",
                "id": queue_id,
            })
        
        for cache_id in model.cache_changes:
            facts.append({
                "type": "cache_change",
                "id": cache_id,
            })
        
        return facts