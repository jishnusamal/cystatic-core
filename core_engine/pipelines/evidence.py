"""
EvidencePipeline — generates semantic evidence from change understanding.

This pipeline is responsible for:
  - Running all semantic analyzers (DomainHub, BusinessObject, etc.)
  - Building EvidenceBundle with all semantic evidence
  - Populating changed_symbols and risk_anchors

Output: EvidenceBundle
"""
from __future__ import annotations

from typing import Any

from core_engine.analysers.analysis_context import AnalysisContext
from core_engine.analysers.business_object_analyzer import BusinessObjectAnalyzer
from core_engine.analysers.cache_dependencies import CacheDependencyAnalyzer
from core_engine.analysers.database_relationships import DatabaseRelationshipAnalyzer
from core_engine.analysers.domain_hub import DomainHubAnalyzer
from core_engine.analysers.event_relationships_analyzer import EventRelationshipAnalyzer
from core_engine.analysers.evidence_registry import EvidenceRegistry
from core_engine.analysers.external_dependencies import ExternalDependencyAnalyzer
from core_engine.analysers.operational_constraints import OperationalConstraintAnalyzer
from core_engine.analysers.ownership import OwnershipAnalyzer
from core_engine.analysers.service_relationships import ServiceRelationshipAnalyzer
from core_engine.analysers.transaction_boundary import TransactionBoundaryAnalyzer
from core_engine.change_influence import extract_changed_symbols
from core_engine.models.change_understanding import ChangeUnderstanding
from core_engine.models.evidence_bundle import EvidenceBundle
from core_engine.models.risk_anchor import RiskAnchor


class EvidencePipeline:
    """Generates semantic evidence from change understanding.
    
    This pipeline owns ALL evidence generation. The orchestrator shouldn't
    even know analyzers exist.
    """
    
    @staticmethod
    def run(understanding: ChangeUnderstanding) -> EvidenceBundle:
        """Run the evidence pipeline.
        
        Args:
            understanding: ChangeUnderstanding from ChangeUnderstandingPipeline.
            
        Returns:
            EvidenceBundle containing all semantic evidence.
        """
        print("Running evidence pipeline...")
        
        # Step 1: Extract changed symbols and risk anchors
        changed_symbols_list = extract_changed_symbols(
            behavior_diffs=understanding.behavior_diffs,
            enriched_files=understanding.enriched_files,
        )
        
        changed_symbols = [
            item for item in changed_symbols_list
            if isinstance(item, dict) and item.get("symbol")
        ]
        
        # Extract risk anchors from risk patterns
        from core_engine.models.enums import RiskAnchorType
        
        risk_anchors = []
        for rp in understanding.risk_patterns:
            rp_dict = rp.model_dump() if hasattr(rp, "model_dump") else (rp if isinstance(rp, dict) else {})
            if rp_dict:
                # Map risk type string to enum
                risk_type_str = rp_dict.get("risk_type", "GENERIC")
                try:
                    anchor_type = RiskAnchorType[risk_type_str]
                except KeyError:
                    anchor_type = RiskAnchorType.GENERIC
                
                symbol = rp_dict.get("symbol", "unknown")
                explanation = rp_dict.get("description", "No description provided")
                
                # Only create RiskAnchor if we have valid data
                if symbol and explanation:
                    risk_anchors.append(RiskAnchor(
                        anchor_type=anchor_type,
                        symbol=symbol,
                        confidence=0.8,  # High confidence from pattern detection
                        explanation=explanation,
                    ))
        
        # Step 2: Build analysis context
        context = AnalysisContext(
            enriched_files=understanding.enriched_files,
            risk_patterns=understanding.risk_patterns,
        )
        
        # Step 3: Create evidence registry
        registry = EvidenceRegistry()
        
        # Step 4: Register and run all semantic analyzers
        analyzers = [
            ("DomainHubAnalyzer", DomainHubAnalyzer()),
            ("BusinessObjectAnalyzer", BusinessObjectAnalyzer()),
            ("TransactionBoundaryAnalyzer", TransactionBoundaryAnalyzer()),
            ("DatabaseRelationshipAnalyzer", DatabaseRelationshipAnalyzer()),
            ("EventRelationshipAnalyzer", EventRelationshipAnalyzer()),
            ("OperationalConstraintAnalyzer", OperationalConstraintAnalyzer()),
            ("ServiceRelationshipAnalyzer", ServiceRelationshipAnalyzer()),
            ("CacheDependencyAnalyzer", CacheDependencyAnalyzer()),
            ("ExternalDependencyAnalyzer", ExternalDependencyAnalyzer()),
            ("OwnershipAnalyzer", OwnershipAnalyzer()),
        ]
        
        for analyzer_name, analyzer in analyzers:
            try:
                print(f"Running {analyzer_name}...")
                output = analyzer.analyze(context)
                registry.ingest_analyzer_output(output, analyzer_name)
            except Exception as e:
                print(f"Analyzer {analyzer_name} failed: {e}")
                continue
        
        # Step 5: Build initial evidence bundle from registry
        initial_bundle = registry.build_bundle()
        
        # Step 6: Build final evidence bundle with all data
        from core_engine.models.changed_symbol import ChangedSymbol
        from core_engine.models.enums import SymbolKind
        
        # Create ChangedSymbol objects from dicts
        changed_symbol_objects = []
        for s in changed_symbols:
            if isinstance(s, dict):
                # Extract kind from dict or default to FUNCTION
                kind_str = s.get("kind", "FUNCTION")
                try:
                    kind = SymbolKind[kind_str] if isinstance(kind_str, str) else SymbolKind.FUNCTION
                except KeyError:
                    kind = SymbolKind.FUNCTION
                
                changed_symbol_objects.append(ChangedSymbol(
                    symbol=s.get("symbol", ""),
                    kind=kind,
                    language=s.get("language", "unknown"),
                    file_path=s.get("file", ""),
                ))
        
        bundle = EvidenceBundle(
            changed_symbols=changed_symbol_objects,
            risk_anchors=risk_anchors,
            impact_evidence=initial_bundle.impact_evidence,
            side_effects=understanding.side_effects,
            constraints=understanding.constraints,
            business_objects=understanding.business_objects,
            domains=initial_bundle.domains,
            confidence=initial_bundle.confidence,
        )
        
        # Step 8: Log statistics
        stats = registry.get_stats()
        print(f"Evidence pipeline complete: {stats['total_evidence']} evidence items from "
              f"{len(stats['analyzer_contributions'])} analyzers")
        
        return bundle