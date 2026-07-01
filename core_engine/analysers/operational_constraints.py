"""
Operational Constraint Analyzer

Extracts invariants and business rules from code.
These become first-class evidence for failure hypothesis generation.

Produces evidence types:
- operational_constraint
- business_invariant
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext
from core_engine.models.enums import EvidenceType


class OperationalConstraintAnalyzer(EvidenceAnalyzer):
    """Extract operational constraints and business invariants.
    
    This analyzer:
    - Identifies validation rules and constraints
    - Detects business invariants
    - Extracts operational requirements
    - Never predicts failures
    - Only extracts deterministic constraint facts
    """
    
    # Constraint patterns to detect
    CONSTRAINT_PATTERNS = {
        # Numeric constraints
        "numeric": {
            "positive": ["must be positive", "> 0", ">= 0", "positive", "non_negative"],
            "range": ["min=", "max=", "between", "range(", "min_value", "max_value"],
            "precision": ["decimal_places", "precision", "round(", "quantize"],
        },
        # String constraints
        "string": {
            "not_empty": ["not empty", "required", "blank=False", "null=False"],
            "length": ["min_length", "max_length", "maxlen", "length"],
            "format": ["email", "phone", "uuid", "regex", "pattern"],
        },
        # Currency/money constraints
        "currency": {
            "match": ["currency must match", "same currency", "currency consistency"],
            "precision": ["2 decimal places", "cents", "minor units"],
            "non_negative": ["amount >= 0", "balance >= 0", "cannot be negative"],
        },
        # Relational constraints
        "relational": {
            "equality": ["total equals", "sum of", "balance =", "invoice total"],
            "comparison": ["must be greater than", "must be less than", "at least", "at most"],
            "uniqueness": ["unique", "unique_together", "no duplicates"],
        },
        # State constraints
        "state": {
            "transition": ["valid transition", "allowed states", "state machine"],
            "invariant": ["must always", "invariant", "never negative", "always positive"],
            "idempotency": ["idempotent", "idempotency", "safe to retry"],
        },
    }
    
    # Business invariant patterns
    INVARIANT_PATTERNS = {
        "financial": [
            "invoice total = subtotal + tax",
            "balance = credits - debits",
            "payment amount = order total",
            "tax = subtotal * rate",
        ],
        "inventory": [
            "stock = incoming - outgoing",
            "available = total - reserved",
        ],
        "user": [
            "user must have email",
            "password must be hashed",
        ],
    }
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract operational constraints from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files and changed functions.
            
        Returns:
            AnalyzerOutput with constraint evidence.
        """
        output = AnalyzerOutput()
        
        # Extract from enriched files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            changed_functions = file_data.get("changed_functions", [])
            keyword_signals = file_data.get("keyword_signals", [])
            
            # Check changed functions for constraint patterns
            for func in changed_functions:
                func_name = self._get_func_name(func)
                if not func_name:
                    continue
                
                func_text = self._get_func_text(func)
                
                # Detect constraints
                constraints = self._detect_constraints(func_text, keyword_signals)
                
                for constraint in constraints:
                    output.constraints.append({
                        "constraint": constraint["name"],
                        "constraint_type": constraint["type"],
                        "value": constraint.get("value", "detected"),
                        "severity": constraint.get("severity", "medium"),
                        "source": func_name,
                        "evidence": constraint["description"],
                        "file_path": file_path,
                    })
                    
                    # Also add as impact evidence
                    output.impact_evidence.append({
                        "source_symbol": func_name,
                        "target_symbol": constraint["name"],
                        "evidence_type": "operational_constraint",
                        "confidence": constraint["confidence"],
                        "explanation": constraint["description"],
                        "metadata": {
                            "constraint_type": constraint["type"],
                            "file_path": file_path,
                        },
                    })
            
            # Check keyword signals for constraint hints
            for signal in keyword_signals:
                signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
                constraints = self._detect_constraints_from_signal(signal_text)
                
                for constraint in constraints:
                    output.constraints.append({
                        "constraint": constraint["name"],
                        "constraint_type": constraint["type"],
                        "value": constraint.get("value", "detected"),
                        "severity": constraint.get("severity", "medium"),
                        "source": "keyword_signal",
                        "evidence": constraint["description"],
                        "file_path": file_path,
                    })
                    
                    output.impact_evidence.append({
                        "source_symbol": file_path,
                        "target_symbol": constraint["name"],
                        "evidence_type": "operational_constraint",
                        "confidence": constraint["confidence"],
                        "explanation": constraint["description"],
                        "metadata": {
                            "constraint_type": constraint["type"],
                            "keyword": signal_text,
                        },
                    })
        
        return output
    
    def _detect_constraints(self, func_text: str, keyword_signals: list) -> list[dict[str, Any]]:
        """Detect constraints in function text.
        
        Args:
            func_text: Function source code or metadata
            keyword_signals: List of keyword signals from analysis
            
        Returns:
            List of constraint dictionaries
        """
        constraints = []
        text_lower = func_text.lower() if func_text else ""
        
        # Check for numeric constraints
        constraints.extend(self._detect_numeric_constraints(text_lower))
        
        # Check for string constraints
        constraints.extend(self._detect_string_constraints(text_lower))
        
        # Check for currency constraints
        constraints.extend(self._detect_currency_constraints(text_lower))
        
        # Check for relational constraints
        constraints.extend(self._detect_relational_constraints(text_lower))
        
        # Check for state constraints
        constraints.extend(self._detect_state_constraints(text_lower))
        
        # Check keyword signals
        for signal in keyword_signals:
            signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
            signal_constraints = self._detect_constraints_from_signal(signal_text)
            constraints.extend(signal_constraints)
        
        # Deduplicate by name
        seen = set()
        unique_constraints = []
        for constraint in constraints:
            if constraint["name"] not in seen:
                seen.add(constraint["name"])
                unique_constraints.append(constraint)
        
        return unique_constraints
    
    def _detect_numeric_constraints(self, text: str) -> list[dict[str, Any]]:
        """Detect numeric constraints."""
        constraints = []
        
        # Positive constraints
        for pattern in self.CONSTRAINT_PATTERNS["numeric"]["positive"]:
            if pattern.lower() in text:
                constraints.append({
                    "name": "must_be_positive",
                    "type": "numeric",
                    "description": "Value must be positive",
                    "confidence": 0.8,
                    "metadata": {"pattern": pattern},
                })
                break
        
        # Range constraints
        for pattern in self.CONSTRAINT_PATTERNS["numeric"]["range"]:
            if pattern.lower() in text:
                constraints.append({
                    "name": "has_range",
                    "type": "numeric",
                    "description": "Value has range constraints",
                    "confidence": 0.75,
                    "metadata": {"pattern": pattern},
                })
                break
        
        return constraints
    
    def _detect_string_constraints(self, text: str) -> list[dict[str, Any]]:
        """Detect string constraints."""
        constraints = []
        
        # Not empty constraints
        for pattern in self.CONSTRAINT_PATTERNS["string"]["not_empty"]:
            if pattern.lower() in text:
                constraints.append({
                    "name": "must_not_be_empty",
                    "type": "string",
                    "description": "String must not be empty",
                    "confidence": 0.8,
                    "metadata": {"pattern": pattern},
                })
                break
        
        # Length constraints
        for pattern in self.CONSTRAINT_PATTERNS["string"]["length"]:
            if pattern.lower() in text:
                constraints.append({
                    "name": "has_length_constraint",
                    "type": "string",
                    "description": "String has length constraints",
                    "confidence": 0.75,
                    "metadata": {"pattern": pattern},
                })
                break
        
        return constraints
    
    def _detect_currency_constraints(self, text: str) -> list[dict[str, Any]]:
        """Detect currency/money constraints."""
        constraints = []
        
        # Currency match
        for pattern in self.CONSTRAINT_PATTERNS["currency"]["match"]:
            if pattern.lower() in text:
                constraints.append({
                    "name": "currency_must_match",
                    "type": "currency",
                    "description": "Currency must match across related entities",
                    "confidence": 0.85,
                    "metadata": {"pattern": pattern},
                })
                break
        
        # Non-negative
        for pattern in self.CONSTRAINT_PATTERNS["currency"]["non_negative"]:
            if pattern.lower() in text:
                constraints.append({
                    "name": "amount_non_negative",
                    "type": "currency",
                    "description": "Amount/balance must never be negative",
                    "confidence": 0.9,
                    "metadata": {"pattern": pattern},
                })
                break
        
        return constraints
    
    def _detect_relational_constraints(self, text: str) -> list[dict[str, Any]]:
        """Detect relational constraints."""
        constraints = []
        
        # Equality constraints
        for pattern in self.CONSTRAINT_PATTERNS["relational"]["equality"]:
            if pattern.lower() in text:
                constraints.append({
                    "name": "has_equality_constraint",
                    "type": "relational",
                    "description": "Values must satisfy equality relationship",
                    "confidence": 0.8,
                    "metadata": {"pattern": pattern},
                })
                break
        
        # Uniqueness constraints
        for pattern in self.CONSTRAINT_PATTERNS["relational"]["uniqueness"]:
            if pattern.lower() in text:
                constraints.append({
                    "name": "must_be_unique",
                    "type": "relational",
                    "description": "Value must be unique",
                    "confidence": 0.85,
                    "metadata": {"pattern": pattern},
                })
                break
        
        return constraints
    
    def _detect_state_constraints(self, text: str) -> list[dict[str, Any]]:
        """Detect state constraints."""
        constraints = []
        
        # Idempotency
        for pattern in self.CONSTRAINT_PATTERNS["state"]["idempotency"]:
            if pattern.lower() in text:
                constraints.append({
                    "name": "must_be_idempotent",
                    "type": "state",
                    "description": "Operation must be idempotent",
                    "confidence": 0.8,
                    "metadata": {"pattern": pattern},
                })
                break
        
        # Invariant
        for pattern in self.CONSTRAINT_PATTERNS["state"]["invariant"]:
            if pattern.lower() in text:
                constraints.append({
                    "name": "has_invariant",
                    "type": "state",
                    "description": "Code maintains an invariant",
                    "confidence": 0.75,
                    "metadata": {"pattern": pattern},
                })
                break
        
        return constraints
    
    def _detect_constraints_from_signal(self, signal_text: str) -> list[dict[str, Any]]:
        """Detect constraints from a keyword signal."""
        constraints = []
        text_lower = signal_text.lower()
        
        # Check all constraint patterns
        for category, patterns in self.CONSTRAINT_PATTERNS.items():
            for constraint_type, keywords in patterns.items():
                for keyword in keywords:
                    if keyword.lower() in text_lower:
                        constraints.append({
                            "name": f"{category}_{constraint_type}",
                            "type": category,
                            "description": f"Detected {constraint_type} constraint from keyword",
                            "confidence": 0.6,
                            "metadata": {"keyword": keyword},
                        })
                        break
        
        return constraints
    
    def _get_func_name(self, func: Any) -> str:
        """Extract function name from function object."""
        if isinstance(func, dict):
            return func.get("name", "")
        if hasattr(func, "model_dump"):
            return func.model_dump().get("name", "")
        if hasattr(func, "name"):
            return func.name
        return ""
    
    def _get_func_text(self, func: Any) -> str:
        """Extract function text/code from function object."""
        if isinstance(func, dict):
            return func.get("text", "") or func.get("code", "") or func.get("name", "")
        if hasattr(func, "model_dump"):
            dump = func.model_dump()
            return dump.get("text", "") or dump.get("code", "") or dump.get("name", "")
        if hasattr(func, "text"):
            return func.text
        if hasattr(func, "code"):
            return func.code
        if hasattr(func, "name"):
            return func.name
        return ""