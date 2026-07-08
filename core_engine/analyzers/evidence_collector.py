"""Evidence Collector - converts analyses into normalized evidence."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from language_adapters.ir.semantic_graph import SemanticGraph

from core_engine.models.compiler_pass import CompilerPass, PassMetadata, PassResult
from core_engine.models.evidence import (
    Evidence,
    ExecutionEvidence,
    CoverageEvidence,
    ArchitectureEvidence,
    CombinedEvidence,
    ExecutionPath,
    EvidenceCategory,
)
from core_engine.models.knowledge_model import KnowledgeModel


class EvidenceCollector(CompilerPass):
    """Converts all previous analyses into normalized evidence.
    
    Every statement becomes:
    Claim -> Proof
    
    Every proof references exact graph nodes.
    """
    
    metadata = PassMetadata(
        name="evidence_collector",
        version="1.0.0",
        description="Converts analyses into normalized evidence",
        produces=["evidence"],
        consumes=[
            "execution_units",
            "interaction_clusters",
            "propagation_paths",
            "coverage",
            "api_changes",
            "event_changes",
            "schema_changes",
            "migration_changes",
            "external_service_calls",
            "queue_changes",
            "cache_changes",
        ],
    )
    
    def execute(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> PassResult:
        """Execute the evidence collection.
        
        Args:
            graph: The semantic graph
            model: The current knowledge model
            
        Returns:
            PassResult with evidence collection results
        """
        diagnostics = []
        evidence_list = []
        
        # Create execution evidence
        if model.execution_units:
            exec_evidence = self._create_execution_evidence(graph, model)
            evidence_list.append(exec_evidence)
        
        # Create coverage evidence
        if model.coverage:
            cov_evidence = self._create_coverage_evidence(graph, model)
            evidence_list.append(cov_evidence)
        
        # Create architecture evidence
        arch_evidence = self._create_architecture_evidence(graph, model)
        evidence_list.append(arch_evidence)
        
        # Create propagation evidence
        if model.propagation_paths:
            prop_evidence = self._create_propagation_evidence(graph, model)
            evidence_list.append(prop_evidence)
        
        # Create surface evidence
        surface_evidence = self._create_surface_evidence(graph, model)
        evidence_list.append(surface_evidence)
        
        # Update model with evidence
        updated_model = model
        for evidence in evidence_list:
            updated_model = updated_model.with_evidence(evidence.evidence_id)
        
        diagnostics.append(
            f"Collected {len(evidence_list)} evidence items"
        )
        
        return PassResult(
            pass_name=self.metadata.name,
            success=True,
            diagnostics=diagnostics,
            metadata={
                "evidence_count": len(evidence_list),
                "evidence_ids": [e.evidence_id for e in evidence_list],
            },
        ), updated_model
    
    def _create_execution_evidence(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> ExecutionEvidence:
        """Create evidence about executable structures."""
        # Collect proof nodes
        proof_nodes = []
        for unit_id in model.execution_units:
            if unit_id.startswith("exec_"):
                node_id = unit_id[5:]  # Remove "exec_" prefix
                if node_id in graph.nodes:
                    proof_nodes.append(node_id)
        
        return ExecutionEvidence(
            evidence_id="evidence_execution",
            category=EvidenceCategory.EXECUTION,
            description="Executable structures in the system",
            claim="The system contains executable structures that can be proven",
            proof=proof_nodes,
            entrypoints=[
                unit_id for unit_id in model.execution_units
                if unit_id.startswith("exec_ENDPOINT:") or unit_id.startswith("exec_TEST:")
            ],
            sinks=[],  # Would be computed by analysis
        )
    
    def _create_coverage_evidence(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> CoverageEvidence:
        """Create evidence about test coverage."""
        return CoverageEvidence(
            evidence_id="evidence_coverage",
            category=EvidenceCategory.COVERAGE,
            description="Test coverage information",
            claim="Test coverage has been analyzed for the system",
            proof=[model.coverage] if model.coverage else [],
        )
    
    def _create_architecture_evidence(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> ArchitectureEvidence:
        """Create evidence about architectural structures."""
        # Collect proof nodes from surface changes
        proof_nodes = []
        proof_nodes.extend(model.api_changes)
        proof_nodes.extend(model.event_changes)
        proof_nodes.extend(model.schema_changes)
        proof_nodes.extend(model.migration_changes)
        proof_nodes.extend(model.external_service_calls)
        
        return ArchitectureEvidence(
            evidence_id="evidence_architecture",
            category=EvidenceCategory.ARCHITECTURE,
            description="Architectural structures in the system",
            claim="The system has architectural structures that can be analyzed",
            proof=proof_nodes,
            new_apis=model.api_changes,
            new_database_access=model.schema_changes,
            new_external_calls=model.external_service_calls,
            new_events=model.event_changes,
            new_schemas=model.schema_changes,
        )
    
    def _create_propagation_evidence(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> Evidence:
        """Create evidence about propagation paths."""
        proof_nodes = []
        for path_id in model.propagation_paths:
            if path_id.startswith("prop_"):
                node_id = path_id[5:]  # Remove "prop_" prefix
                if node_id in graph.nodes:
                    proof_nodes.append(node_id)
        
        return Evidence(
            evidence_id="evidence_propagation",
            category=EvidenceCategory.PROPAGATION,
            description="Propagation paths from changed nodes",
            claim="Changed nodes have deterministic reachability to other nodes",
            proof=proof_nodes,
        )
    
    def _create_surface_evidence(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> Evidence:
        """Create evidence about external surface changes."""
        proof_nodes = []
        proof_nodes.extend(model.api_changes)
        proof_nodes.extend(model.event_changes)
        proof_nodes.extend(model.schema_changes)
        proof_nodes.extend(model.migration_changes)
        proof_nodes.extend(model.external_service_calls)
        proof_nodes.extend(model.queue_changes)
        proof_nodes.extend(model.cache_changes)
        
        return Evidence(
            evidence_id="evidence_surface",
            category=EvidenceCategory.SURFACE,
            description="Externally observable interface changes",
            claim="The system has externally observable interfaces that have changed",
            proof=proof_nodes,
        )