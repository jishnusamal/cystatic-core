"""
Transaction Boundary Analyzer

Detects transaction boundaries and state management patterns.
This dramatically improves reasoning around state changes and consistency.

Produces evidence types:
- starts_transaction
- inside_transaction
- commits_transaction
- rolls_back_transaction
- shared_transaction
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext
from core_engine.models.enums import EvidenceType


class TransactionBoundaryAnalyzer(EvidenceAnalyzer):
    """Detect transaction boundaries and state management.
    
    This analyzer:
    - Identifies transaction decorators and context managers
    - Detects unit of work patterns
    - Maps transaction boundaries across services
    - Never predicts failures
    - Only extracts deterministic transaction facts
    """
    
    # Transaction patterns to detect
    TRANSACTION_PATTERNS = {
        # Decorators
        "decorators": [
            "transaction.atomic",
            "transaction.atomic(atomic=True)",
            "transaction.atomic(atomic=False)",
            "@transaction.atomic",
            "transaction.atomic()",
        ],
        # Context managers
        "context_managers": [
            "transaction.atomic()",
            "with transaction.atomic():",
            "with transaction.atomic() as txn:",
        ],
        # Unit of work patterns
        "unit_of_work": [
            "begin_transaction",
            "commit_transaction",
            "rollback_transaction",
            "unit_of_work",
            "uow",
            "UnitOfWork",
            "start_transaction",
            "end_transaction",
        ],
        # Session patterns (SQLAlchemy, Django ORM)
        "session_patterns": [
            "session.commit",
            "session.rollback",
            "session.flush",
            "db.session.commit",
            "db.session.rollback",
        ],
    }
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract transaction boundaries from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files and changed functions.
            
        Returns:
            AnalyzerOutput with transaction evidence.
        """
        output = AnalyzerOutput()
        
        # Track transactions and their participants
        transactions: dict[str, list[str]] = {}  # transaction_id -> list of symbols
        transaction_participants: dict[str, str] = {}  # symbol -> transaction_id
        
        # Extract from enriched files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            changed_functions = file_data.get("changed_functions", [])
            keyword_signals = file_data.get("keyword_signals", [])
            
            # Check changed functions for transaction patterns
            for func in changed_functions:
                func_name = self._get_func_name(func)
                if not func_name:
                    continue
                
                func_text = self._get_func_text(func)
                
                # Check for transaction decorators
                txn_info = self._detect_transaction_pattern(func_text, keyword_signals)
                
                if txn_info["has_transaction"]:
                    txn_id = f"{file_path}::{func_name}"
                    
                    # Add evidence that this function starts/manages a transaction
                    if txn_info["starts_transaction"]:
                        output.impact_evidence.append({
                            "source_symbol": func_name,
                            "target_symbol": "transaction_boundary",
                            "evidence_type": "starts_transaction",
                            "confidence": 0.9,
                            "explanation": f"Function {func_name} starts a transaction",
                            "metadata": {
                                "file_path": file_path,
                                "pattern": txn_info["pattern"],
                                "transaction_id": txn_id,
                            },
                        })
                        
                        transactions[txn_id] = [func_name]
                        transaction_participants[func_name] = txn_id
                    
                    if txn_info["commits_transaction"]:
                        output.impact_evidence.append({
                            "source_symbol": func_name,
                            "target_symbol": "transaction_boundary",
                            "evidence_type": "commits_transaction",
                            "confidence": 0.85,
                            "explanation": f"Function {func_name} commits a transaction",
                            "metadata": {
                                "file_path": file_path,
                                "pattern": txn_info["pattern"],
                                "transaction_id": txn_id,
                            },
                        })
                    
                    if txn_info["rolls_back_transaction"]:
                        output.impact_evidence.append({
                            "source_symbol": func_name,
                            "target_symbol": "transaction_boundary",
                            "evidence_type": "rolls_back_transaction",
                            "confidence": 0.85,
                            "explanation": f"Function {func_name} can rollback a transaction",
                            "metadata": {
                                "file_path": file_path,
                                "pattern": txn_info["pattern"],
                                "transaction_id": txn_id,
                            },
                        })
                    
                    if txn_info["inside_transaction"]:
                        output.impact_evidence.append({
                            "source_symbol": func_name,
                            "target_symbol": "transaction_boundary",
                            "evidence_type": "inside_transaction",
                            "confidence": 0.8,
                            "explanation": f"Function {func_name} executes inside a transaction",
                            "metadata": {
                                "file_path": file_path,
                                "pattern": txn_info["pattern"],
                                "transaction_id": txn_id,
                            },
                        })
                        
                        # Track transaction participants
                        if txn_id in transactions:
                            if func_name not in transactions[txn_id]:
                                transactions[txn_id].append(func_name)
            
            # Check keyword signals for transaction hints
            for signal in keyword_signals:
                signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
                if self._is_transaction_keyword(signal_text):
                    output.impact_evidence.append({
                        "source_symbol": file_path,
                        "target_symbol": "transaction_boundary",
                        "evidence_type": "inside_transaction",
                        "confidence": 0.6,
                        "explanation": f"Keyword signal suggests transaction usage",
                        "metadata": {
                            "keyword": signal_text,
                            "file_path": file_path,
                        },
                    })
        
        # Generate shared transaction evidence
        # If multiple functions participate in the same transaction, they're connected
        for txn_id, participants in transactions.items():
            if len(participants) > 1:
                for i, func1 in enumerate(participants):
                    for func2 in participants[i+1:]:
                        output.impact_evidence.append({
                            "source_symbol": func1,
                            "target_symbol": func2,
                            "evidence_type": "shared_transaction",
                            "confidence": 0.8,
                            "explanation": f"Both functions participate in the same transaction",
                            "metadata": {
                                "transaction_id": txn_id,
                            },
                        })
        
        return output
    
    def _detect_transaction_pattern(self, func_text: str, keyword_signals: list) -> dict[str, bool]:
        """Detect transaction patterns in function text.
        
        Args:
            func_text: Function source code or metadata
            keyword_signals: List of keyword signals from analysis
            
        Returns:
            Dictionary with transaction pattern flags
        """
        result = {
            "has_transaction": False,
            "starts_transaction": False,
            "commits_transaction": False,
            "rolls_back_transaction": False,
            "inside_transaction": False,
            "pattern": None,
        }
        
        text_lower = func_text.lower() if func_text else ""
        
        # Check for decorators
        for pattern in self.TRANSACTION_PATTERNS["decorators"]:
            if pattern.lower() in text_lower:
                result["has_transaction"] = True
                result["starts_transaction"] = True
                result["pattern"] = "decorator"
                break
        
        # Check for context managers
        if not result["has_transaction"]:
            for pattern in self.TRANSACTION_PATTERNS["context_managers"]:
                if pattern.lower() in text_lower:
                    result["has_transaction"] = True
                    result["starts_transaction"] = True
                    result["pattern"] = "context_manager"
                    break
        
        # Check for unit of work patterns
        if not result["has_transaction"]:
            for pattern in self.TRANSACTION_PATTERNS["unit_of_work"]:
                if pattern.lower() in text_lower:
                    result["has_transaction"] = True
                    result["starts_transaction"] = True
                    result["pattern"] = "unit_of_work"
                    break
        
        # Check for commit/rollback
        for pattern in self.TRANSACTION_PATTERNS["session_patterns"]:
            if "commit" in pattern.lower() and pattern.lower() in text_lower:
                result["commits_transaction"] = True
                result["has_transaction"] = True
            if "rollback" in pattern.lower() and pattern.lower() in text_lower:
                result["rolls_back_transaction"] = True
                result["has_transaction"] = True
        
        # Check keyword signals
        for signal in keyword_signals:
            signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
            if self._is_transaction_keyword(signal_text):
                result["inside_transaction"] = True
                result["has_transaction"] = True
                break
        
        return result
    
    def _is_transaction_keyword(self, keyword: str) -> bool:
        """Check if a keyword is transaction-related."""
        keyword_lower = keyword.lower()
        transaction_keywords = [
            "transaction",
            "atomic",
            "commit",
            "rollback",
            "unit of work",
            "uow",
            "session",
        ]
        return any(kw in keyword_lower for kw in transaction_keywords)
    
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