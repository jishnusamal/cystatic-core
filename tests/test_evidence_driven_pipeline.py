"""
Test the new evidence-driven analysis pipeline.

This test validates:
1. AnalysisContext creation
2. Analyzer registry execution
3. EvidenceBundle generation
4. Hypothesis generation
5. Scenario generation
"""
from __future__ import annotations

import pytest
from core_engine.analysers.analysis_context import AnalysisContext
from core_engine.analysers.registry import AnalyzerRegistry
from core_engine.analysers.changed_symbols import ChangedSymbolAnalyzer
from core_engine.analysers.side_effects import SideEffectAnalyzer
from core_engine.analysers.business_objects import BusinessObjectAnalyzer
from core_engine.analysers.risk_anchors import RiskAnchorAnalyzer
from core_engine.analysers.event_relationships import EventRelationshipAnalyzer
from core_engine.hypothesis.generator import HypothesisGenerator
from core_engine.scenarios.generator import FailureScenarioGenerator


def test_analysis_context_creation():
    """Test that AnalysisContext can be created with minimal data."""
    context = AnalysisContext(
        enriched_files=[
            {
                "file_path": "payment/process.py",
                "changed_functions": [
                    {"name": "process_payment", "type": "function"}
                ],
                "hunks": [
                    {
                        "lines": [
                            {"line_type": "added", "content": "def process_payment():"}
                        ]
                    }
                ],
                "keyword_signals": [],
            }
        ],
        risk_patterns=[],
    )
    
    assert len(context.enriched_files) == 1
    assert context.enriched_files[0]["file_path"] == "payment/process.py"


def test_changed_symbol_analyzer():
    """Test ChangedSymbolAnalyzer extracts symbols correctly."""
    context = AnalysisContext(
        enriched_files=[
            {
                "file_path": "payment/process.py",
                "changed_functions": [
                    {"name": "process_payment", "type": "function"},
                    {"name": "PaymentService", "type": "class"},
                ],
                "hunks": [],
                "keyword_signals": [],
            }
        ],
        risk_patterns=[],
    )
    
    analyzer = ChangedSymbolAnalyzer()
    output = analyzer.analyze(context)
    
    assert len(output.changed_symbols) == 2
    assert output.changed_symbols[0]["symbol"] == "process_payment"
    assert output.changed_symbols[0]["kind"] == "function"
    assert output.changed_symbols[1]["symbol"] == "PaymentService"
    assert output.changed_symbols[1]["kind"] == "class"


def test_side_effect_analyzer():
    """Test SideEffectAnalyzer detects side effects correctly."""
    context = AnalysisContext(
        enriched_files=[
            {
                "file_path": "payment/process.py",
                "changed_functions": [],
                "hunks": [
                    {
                        "lines": [
                            {"line_type": "added", "content": "db.session.add(payment)"},
                            {"line_type": "added", "content": "requests.post('https://api.example.com')"},
                        ]
                    }
                ],
                "keyword_signals": [],
            }
        ],
        risk_patterns=[],
    )
    
    analyzer = SideEffectAnalyzer()
    output = analyzer.analyze(context)
    
    assert len(output.side_effects) >= 2
    effect_types = [se["effect_type"] for se in output.side_effects]
    assert "database_write" in effect_types
    assert "http_call" in effect_types


def test_business_object_analyzer():
    """Test BusinessObjectAnalyzer identifies business objects correctly."""
    context = AnalysisContext(
        enriched_files=[
            {
                "file_path": "payment/process_payment.py",
                "changed_functions": [
                    {"name": "process_payment", "type": "function"},
                ],
                "hunks": [],
                "keyword_signals": [],
            }
        ],
        risk_patterns=[],
    )
    
    analyzer = BusinessObjectAnalyzer()
    output = analyzer.analyze(context)
    
    assert len(output.business_objects) >= 1
    business_object_names = [bo["name"] for bo in output.business_objects]
    assert "Payment" in business_object_names


def test_risk_anchor_analyzer():
    """Test RiskAnchorAnalyzer identifies risk anchors correctly."""
    context = AnalysisContext(
        enriched_files=[
            {
                "file_path": "payment/process_payment.py",
                "changed_functions": [
                    {"name": "process_payment", "type": "function"},
                ],
                "hunks": [],
                "keyword_signals": [],
            }
        ],
        risk_patterns=[],
    )
    
    analyzer = RiskAnchorAnalyzer()
    output = analyzer.analyze(context)
    
    assert len(output.risk_anchors) >= 1
    anchor_types = [ra["anchor_type"] for ra in output.risk_anchors]
    assert "money_flow" in anchor_types


def test_analyzer_registry():
    """Test AnalyzerRegistry executes all analyzers and aggregates results."""
    context = AnalysisContext(
        enriched_files=[
            {
                "file_path": "payment/process_payment.py",
                "changed_functions": [
                    {"name": "process_payment", "type": "function"},
                ],
                "hunks": [
                    {
                        "lines": [
                            {"line_type": "added", "content": "db.session.add(payment)"},
                        ]
                    }
                ],
                "keyword_signals": [],
            }
        ],
        risk_patterns=[],
    )
    
    registry = AnalyzerRegistry()
    registry.register(ChangedSymbolAnalyzer())
    registry.register(SideEffectAnalyzer())
    registry.register(BusinessObjectAnalyzer())
    registry.register(RiskAnchorAnalyzer())
    
    bundle = registry.analyze_all(context)
    
    # Verify bundle contains evidence from all analyzers
    assert len(bundle.changed_symbols) >= 1
    assert len(bundle.side_effects) >= 1
    assert len(bundle.business_objects) >= 1
    assert len(bundle.risk_anchors) >= 1


def test_hypothesis_generator():
    """Test HypothesisGenerator creates hypotheses from evidence bundle."""
    from core_engine.models.evidence_bundle import EvidenceBundle
    from core_engine.models.changed_symbol import ChangedSymbol
    from core_engine.models.risk_anchor import RiskAnchor
    from core_engine.models.impact_evidence import ImpactEvidence
    from core_engine.models.entity_ref import EntityRef
    
    bundle = EvidenceBundle(
        changed_symbols=[
            ChangedSymbol(
                symbol="process_payment",
                qualified_name="payment/process.py:process_payment",
                kind="function",
                language="python",
                file_path="payment/process.py",
                module="payment.process",
                extraction_confidence=1.0,
            )
        ],
        risk_anchors=[
            RiskAnchor(
                anchor_type="money_flow",
                symbol="process_payment",
                confidence=0.8,
                business_domain="payment",
                business_object="Payment",
                characteristics=["payment"],
                explanation="Payment processing function",
            )
        ],
        impact_evidence=[
            ImpactEvidence(
                source=EntityRef(kind="symbol", id="process_payment", name="process_payment"),
                target=EntityRef(kind="symbol", id="create_invoice", name="create_invoice"),
                evidence_type="domain_relationship",
                confidence=0.7,
                explanation="Payment and billing are related domains",
            )
        ],
        side_effects=[
            {
                "description": "Database write",
                "symbol": "payment/process.py",
                "effect_type": "database_write",
                "confidence": 0.8,
            }
        ],
        business_objects=[
            {"name": "Payment", "domain": "payment"},
        ],
        domains=["payment", "billing"],
    )
    
    generator = HypothesisGenerator()
    hypotheses = generator.generate(bundle)
    
    assert len(hypotheses) >= 1
    # Check that hypotheses have required fields
    for hypothesis in hypotheses:
        assert hypothesis.confidence > 0.0
        assert hypothesis.confidence <= 1.0
        assert hypothesis.impact_type is not None


def test_scenario_generator():
    """Test FailureScenarioGenerator creates scenarios from hypotheses."""
    from core_engine.models.impact_hypothesis import ImpactHypothesis
    
    hypotheses = [
        ImpactHypothesis(
            hypothesis="Payment processing may impact invoice creation",
            confidence=0.75,
            source_symbol="payment/process.py:process_payment",
            target_symbol="billing/invoice.py:create_invoice",
            impact_type="financial_impact",
            description="Payment processing may impact invoice creation",
            evidence_summary="Payment and billing domains are related",
            affected_business_objects=["Payment", "Invoice"],
            affected_domains=["payment", "billing"],
        )
    ]
    
    generator = FailureScenarioGenerator()
    scenarios = generator.generate(hypotheses)
    
    assert len(scenarios) >= 1
    # Check that scenarios have required fields
    for scenario in scenarios:
        assert scenario.title is not None
        assert scenario.confidence > 0.0
        assert scenario.merge_risk_level in ["HIGH", "MEDIUM", "LOW"]
        assert scenario.failure_class is not None


def test_full_pipeline_integration():
    """Test the full evidence-driven pipeline integration."""
    # Create a minimal context
    context = AnalysisContext(
        enriched_files=[
            {
                "file_path": "payment/process_payment.py",
                "changed_functions": [
                    {"name": "process_payment", "type": "function"},
                ],
                "hunks": [
                    {
                        "lines": [
                            {"line_type": "added", "content": "db.session.add(payment)"},
                            {"line_type": "added", "content": "publish_event('payment_processed')"},
                        ]
                    }
                ],
                "keyword_signals": [],
            }
        ],
        risk_patterns=[],
    )
    
    # Run analyzers
    registry = AnalyzerRegistry()
    registry.register(ChangedSymbolAnalyzer())
    registry.register(SideEffectAnalyzer())
    registry.register(BusinessObjectAnalyzer())
    registry.register(RiskAnchorAnalyzer())
    registry.register(EventRelationshipAnalyzer())
    
    bundle = registry.analyze_all(context)
    
    # Verify bundle
    assert len(bundle.changed_symbols) >= 1
    assert len(bundle.side_effects) >= 2  # database_write and queue_publish
    
    # Generate hypotheses
    hypothesis_generator = HypothesisGenerator()
    hypotheses = hypothesis_generator.generate(bundle)
    
    assert len(hypotheses) >= 1
    
    # Generate scenarios
    scenario_generator = FailureScenarioGenerator()
    scenarios = scenario_generator.generate(hypotheses)
    
    assert len(scenarios) >= 1
    
    # Verify scenarios have reasonable properties
    for scenario in scenarios:
        assert 0.0 <= scenario.confidence <= 1.0
        assert scenario.merge_risk_level in ["HIGH", "MEDIUM", "LOW"]
        assert scenario.title is not None