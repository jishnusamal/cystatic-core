"""Surface Analyzer - discovers externally observable interfaces."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from language_adapters.ir.semantic_graph import SemanticGraph
from language_adapters.ir.nodes import BaseNode, NodeType
from language_adapters.ir.edges import BaseEdge, EdgeType

from core_engine.models.compiler_pass import CompilerPass, PassMetadata, PassResult
from core_engine.models.knowledge_model import KnowledgeModel


class SurfaceAnalyzer(CompilerPass):
    """Discovers externally observable interfaces.
    
    Produces:
    - API changes
    - Event changes
    - Schema changes
    - Migration changes
    - External service calls
    - Queue changes
    - Cache changes
    
    Everything is traceable to graph nodes.
    """
    
    metadata = PassMetadata(
        name="surface_analyzer",
        version="1.0.0",
        description="Discovers externally observable interfaces",
        produces=[
            "api_changes",
            "event_changes",
            "schema_changes",
            "migration_changes",
            "external_service_calls",
            "queue_changes",
            "cache_changes",
        ],
        consumes=["execution_units"],
    )
    
    def execute(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> PassResult:
        """Execute the surface analysis.
        
        Args:
            graph: The semantic graph
            model: The current knowledge model
            
        Returns:
            PassResult with surface analysis results
        """
        diagnostics = []
        
        # Discover API changes
        api_changes = self._find_api_changes(graph)
        
        # Discover event changes
        event_changes = self._find_event_changes(graph)
        
        # Discover schema changes
        schema_changes = self._find_schema_changes(graph)
        
        # Discover migration changes
        migration_changes = self._find_migration_changes(graph)
        
        # Discover external service calls
        external_service_calls = self._find_external_service_calls(graph)
        
        # Discover queue changes
        queue_changes = self._find_queue_changes(graph)
        
        # Discover cache changes
        cache_changes = self._find_cache_changes(graph)
        
        # Update model with all surface changes
        updated_model = model
        for api_id in api_changes:
            updated_model = KnowledgeModel(
                graph_id=updated_model.graph_id,
                commit_hash=updated_model.commit_hash,
                execution_units=updated_model.execution_units,
                interaction_clusters=updated_model.interaction_clusters,
                propagation_paths=updated_model.propagation_paths,
                coverage=updated_model.coverage,
                evidence=updated_model.evidence,
                signals=updated_model.signals,
                api_changes=updated_model.api_changes + [api_id],
                event_changes=updated_model.event_changes,
                schema_changes=updated_model.schema_changes,
                migration_changes=updated_model.migration_changes,
                external_service_calls=updated_model.external_service_calls,
                queue_changes=updated_model.queue_changes,
                cache_changes=updated_model.cache_changes,
                pass_metadata=updated_model.pass_metadata,
                diagnostics=updated_model.diagnostics,
            )
        
        for event_id in event_changes:
            updated_model = KnowledgeModel(
                graph_id=updated_model.graph_id,
                commit_hash=updated_model.commit_hash,
                execution_units=updated_model.execution_units,
                interaction_clusters=updated_model.interaction_clusters,
                propagation_paths=updated_model.propagation_paths,
                coverage=updated_model.coverage,
                evidence=updated_model.evidence,
                signals=updated_model.signals,
                api_changes=updated_model.api_changes,
                event_changes=updated_model.event_changes + [event_id],
                schema_changes=updated_model.schema_changes,
                migration_changes=updated_model.migration_changes,
                external_service_calls=updated_model.external_service_calls,
                queue_changes=updated_model.queue_changes,
                cache_changes=updated_model.cache_changes,
                pass_metadata=updated_model.pass_metadata,
                diagnostics=updated_model.diagnostics,
            )
        
        for schema_id in schema_changes:
            updated_model = KnowledgeModel(
                graph_id=updated_model.graph_id,
                commit_hash=updated_model.commit_hash,
                execution_units=updated_model.execution_units,
                interaction_clusters=updated_model.interaction_clusters,
                propagation_paths=updated_model.propagation_paths,
                coverage=updated_model.coverage,
                evidence=updated_model.evidence,
                signals=updated_model.signals,
                api_changes=updated_model.api_changes,
                event_changes=updated_model.event_changes,
                schema_changes=updated_model.schema_changes + [schema_id],
                migration_changes=updated_model.migration_changes,
                external_service_calls=updated_model.external_service_calls,
                queue_changes=updated_model.queue_changes,
                cache_changes=updated_model.cache_changes,
                pass_metadata=updated_model.pass_metadata,
                diagnostics=updated_model.diagnostics,
            )
        
        for migration_id in migration_changes:
            updated_model = KnowledgeModel(
                graph_id=updated_model.graph_id,
                commit_hash=updated_model.commit_hash,
                execution_units=updated_model.execution_units,
                interaction_clusters=updated_model.interaction_clusters,
                propagation_paths=updated_model.propagation_paths,
                coverage=updated_model.coverage,
                evidence=updated_model.evidence,
                signals=updated_model.signals,
                api_changes=updated_model.api_changes,
                event_changes=updated_model.event_changes,
                schema_changes=updated_model.schema_changes,
                migration_changes=updated_model.migration_changes + [migration_id],
                external_service_calls=updated_model.external_service_calls,
                queue_changes=updated_model.queue_changes,
                cache_changes=updated_model.cache_changes,
                pass_metadata=updated_model.pass_metadata,
                diagnostics=updated_model.diagnostics,
            )
        
        for ext_id in external_service_calls:
            updated_model = KnowledgeModel(
                graph_id=updated_model.graph_id,
                commit_hash=updated_model.commit_hash,
                execution_units=updated_model.execution_units,
                interaction_clusters=updated_model.interaction_clusters,
                propagation_paths=updated_model.propagation_paths,
                coverage=updated_model.coverage,
                evidence=updated_model.evidence,
                signals=updated_model.signals,
                api_changes=updated_model.api_changes,
                event_changes=updated_model.event_changes,
                schema_changes=updated_model.schema_changes,
                migration_changes=updated_model.migration_changes,
                external_service_calls=updated_model.external_service_calls + [ext_id],
                queue_changes=updated_model.queue_changes,
                cache_changes=updated_model.cache_changes,
                pass_metadata=updated_model.pass_metadata,
                diagnostics=updated_model.diagnostics,
            )
        
        for queue_id in queue_changes:
            updated_model = KnowledgeModel(
                graph_id=updated_model.graph_id,
                commit_hash=updated_model.commit_hash,
                execution_units=updated_model.execution_units,
                interaction_clusters=updated_model.interaction_clusters,
                propagation_paths=updated_model.propagation_paths,
                coverage=updated_model.coverage,
                evidence=updated_model.evidence,
                signals=updated_model.signals,
                api_changes=updated_model.api_changes,
                event_changes=updated_model.event_changes,
                schema_changes=updated_model.schema_changes,
                migration_changes=updated_model.migration_changes,
                external_service_calls=updated_model.external_service_calls,
                queue_changes=updated_model.queue_changes + [queue_id],
                cache_changes=updated_model.cache_changes,
                pass_metadata=updated_model.pass_metadata,
                diagnostics=updated_model.diagnostics,
            )
        
        for cache_id in cache_changes:
            updated_model = KnowledgeModel(
                graph_id=updated_model.graph_id,
                commit_hash=updated_model.commit_hash,
                execution_units=updated_model.execution_units,
                interaction_clusters=updated_model.interaction_clusters,
                propagation_paths=updated_model.propagation_paths,
                coverage=updated_model.coverage,
                evidence=updated_model.evidence,
                signals=updated_model.signals,
                api_changes=updated_model.api_changes,
                event_changes=updated_model.event_changes,
                schema_changes=updated_model.schema_changes,
                migration_changes=updated_model.migration_changes,
                external_service_calls=updated_model.external_service_calls,
                queue_changes=updated_model.queue_changes,
                cache_changes=updated_model.cache_changes + [cache_id],
                pass_metadata=updated_model.pass_metadata,
                diagnostics=updated_model.diagnostics,
            )
        
        diagnostics.append(
            f"Surface changes: {len(api_changes)} APIs, {len(event_changes)} events, "
            f"{len(schema_changes)} schemas, {len(migration_changes)} migrations, "
            f"{len(external_service_calls)} external services, {len(queue_changes)} queues, "
            f"{len(cache_changes)} caches"
        )
        
        return PassResult(
            pass_name=self.metadata.name,
            success=True,
            diagnostics=diagnostics,
            metadata={
                "api_changes_count": len(api_changes),
                "event_changes_count": len(event_changes),
                "schema_changes_count": len(schema_changes),
                "migration_changes_count": len(migration_changes),
                "external_service_calls_count": len(external_service_calls),
                "queue_changes_count": len(queue_changes),
                "cache_changes_count": len(cache_changes),
            },
        ), updated_model
    
    def _find_api_changes(self, graph: SemanticGraph) -> List[str]:
        """Find API endpoint changes."""
        apis = []
        for node_id, node in graph.nodes.items():
            if node.node_type == NodeType.ENDPOINT:
                if node.change_type in ("added", "modified", "removed"):
                    apis.append(node_id)
        return apis
    
    def _find_event_changes(self, graph: SemanticGraph) -> List[str]:
        """Find event changes."""
        events = []
        for node_id, node in graph.nodes.items():
            if node.node_type == NodeType.EVENT:
                if node.change_type in ("added", "modified", "removed"):
                    events.append(node_id)
        return events
    
    def _find_schema_changes(self, graph: SemanticGraph) -> List[str]:
        """Find schema changes (models, fields)."""
        schemas = []
        for node_id, node in graph.nodes.items():
            if node.node_type in (NodeType.MODEL, NodeType.FIELD):
                if node.change_type in ("added", "modified", "removed"):
                    schemas.append(node_id)
        return schemas
    
    def _find_migration_changes(self, graph: SemanticGraph) -> List[str]:
        """Find migration changes."""
        migrations = []
        for node_id, node in graph.nodes.items():
            if node.node_type == NodeType.MIGRATION:
                if node.change_type in ("added", "modified", "removed"):
                    migrations.append(node_id)
        return migrations
    
    def _find_external_service_calls(self, graph: SemanticGraph) -> List[str]:
        """Find external service calls."""
        services = []
        
        # Look for EXTERNAL_SERVICE nodes
        for node_id, node in graph.nodes.items():
            if node.node_type == NodeType.EXTERNAL_SERVICE:
                if node.change_type in ("added", "modified", "removed"):
                    services.append(node_id)
        
        # Look for edges to external services
        for edge in graph.edges:
            if edge.edge_type == EdgeType.SENDS_HTTP:
                target_id = graph._node_key(edge.target)
                if target_id not in services:
                    services.append(target_id)
        
        return services
    
    def _find_queue_changes(self, graph: SemanticGraph) -> List[str]:
        """Find queue changes."""
        queues = []
        for node_id, node in graph.nodes.items():
            if node.node_type == NodeType.QUEUE:
                if node.change_type in ("added", "modified", "removed"):
                    queues.append(node_id)
        return queues
    
    def _find_cache_changes(self, graph: SemanticGraph) -> List[str]:
        """Find cache changes."""
        caches = []
        for node_id, node in graph.nodes.items():
            if node.node_type == NodeType.CACHE:
                if node.change_type in ("added", "modified", "removed"):
                    caches.append(node_id)
        return caches