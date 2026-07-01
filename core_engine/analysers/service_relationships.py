"""
Service Relationship Analyzer

Infers architectural service relationships from code structure.
This adds architectural context without execution-path reasoning.

Produces evidence types:
- same_service
- calls_service
- depends_on_service
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext
from core_engine.models.enums import EvidenceType


class ServiceRelationshipAnalyzer(EvidenceAnalyzer):
    """Infer architectural service relationships.
    
    This analyzer:
    - Identifies service boundaries from code structure
    - Detects service-to-service dependencies
    - Maps architectural relationships
    - Never traces execution paths
    - Only extracts deterministic architectural facts
    """
    
    # Service boundary indicators
    SERVICE_INDICATORS = {
        # Directory/module patterns
        "directory_patterns": [
            "services/",
            "service/",
            "modules/",
            "module/",
            "handlers/",
            "controllers/",
            "apis/",
            "endpoints/",
        ],
        # Class/function patterns
        "service_patterns": [
            "Service",
            "Handler",
            "Controller",
            "Manager",
            "Client",
            "Adapter",
        ],
        # Import patterns
        "import_patterns": [
            "from .services",
            "from services",
            "from modules",
            "import service",
        ],
    }
    
    # Service naming conventions
    SERVICE_NAMES = {
        "payment": ["PaymentService", "PaymentHandler", "PaymentClient"],
        "billing": ["BillingService", "BillingHandler", "InvoiceService"],
        "order": ["OrderService", "OrderHandler", "OrderManager"],
        "user": ["UserService", "UserHandler", "UserManager", "CustomerService"],
        "auth": ["AuthService", "AuthHandler", "AuthenticationService"],
        "notification": ["NotificationService", "NotificationHandler", "EmailService"],
        "inventory": ["InventoryService", "InventoryHandler", "StockService"],
        "shipping": ["ShippingService", "ShippingHandler", "FulfillmentService"],
    }
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract service relationships from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files and changed functions.
            
        Returns:
            AnalyzerOutput with service relationship evidence.
        """
        output = AnalyzerOutput()
        
        # Track services and their components
        services: dict[str, list[str]] = {}  # service_name -> list of symbols
        service_dependencies: dict[str, set[str]] = {}  # service -> set of dependent services
        
        # Extract from enriched files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            changed_functions = file_data.get("changed_functions", [])
            
            # Identify service from file path
            service_name = self._identify_service_from_path(file_path)
            
            if service_name:
                if service_name not in services:
                    services[service_name] = []
                    service_dependencies[service_name] = set()
                
                # Add file to service
                if file_path not in services[service_name]:
                    services[service_name].append(file_path)
                
                # Add evidence that file belongs to service
                output.impact_evidence.append({
                    "source_symbol": file_path,
                    "target_symbol": service_name,
                    "evidence_type": "same_service",
                    "confidence": 0.9,
                    "explanation": f"File belongs to {service_name} service",
                    "metadata": {
                        "artifact_type": "file",
                        "service": service_name,
                    },
                })
                
                # Add changed functions
                for func in changed_functions:
                    func_name = self._get_func_name(func)
                    if func_name:
                        if func_name not in services[service_name]:
                            services[service_name].append(func_name)
                        
                        output.impact_evidence.append({
                            "source_symbol": func_name,
                            "target_symbol": service_name,
                            "evidence_type": "same_service",
                            "confidence": 0.85,
                            "explanation": f"Function belongs to {service_name} service",
                            "metadata": {
                                "artifact_type": "function",
                                "service": service_name,
                                "file_path": file_path,
                            },
                        })
                        
                        # Detect service dependencies from function
                        func_text = self._get_func_text(func)
                        dependencies = self._detect_service_dependencies(func_text, service_name)
                        
                        for dep_service in dependencies:
                            service_dependencies[service_name].add(dep_service)
            
            # Check keyword signals for service hints
            keyword_signals = file_data.get("keyword_signals", [])
            for signal in keyword_signals:
                signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
                signal_service = self._identify_service_from_text(signal_text)
                
                if signal_service and signal_service != service_name:
                    output.impact_evidence.append({
                        "source_symbol": file_path,
                        "target_symbol": signal_service,
                        "evidence_type": "depends_on_service",
                        "confidence": 0.6,
                        "explanation": f"Keyword signal suggests dependency on {signal_service}",
                        "metadata": {
                            "keyword": signal_text,
                            "source_service": service_name,
                            "target_service": signal_service,
                        },
                    })
        
        # Generate service dependency evidence
        for service, dependencies in service_dependencies.items():
            for dep_service in dependencies:
                output.impact_evidence.append({
                    "source_symbol": service,
                    "target_symbol": dep_service,
                    "evidence_type": "depends_on_service",
                    "confidence": 0.75,
                    "explanation": f"{service} service depends on {dep_service} service",
                    "metadata": {
                        "dependency_type": "architectural",
                    },
                })
        
        # Generate same_service evidence for files in same service
        for service_name, symbols in services.items():
            if len(symbols) > 1:
                for i, sym1 in enumerate(symbols):
                    for sym2 in symbols[i+1:]:
                        output.impact_evidence.append({
                            "source_symbol": sym1,
                            "target_symbol": sym2,
                            "evidence_type": "same_service",
                            "confidence": 0.8,
                            "explanation": f"Both belong to {service_name} service",
                            "metadata": {
                                "service": service_name,
                            },
                        })
        
        return output
    
    def _identify_service_from_path(self, file_path: str) -> str | None:
        """Identify service from file path."""
        path_lower = file_path.lower()
        
        # Check directory patterns
        for pattern in self.SERVICE_INDICATORS["directory_patterns"]:
            if pattern in path_lower:
                # Extract service name from path
                parts = path_lower.split("/")
                for part in parts:
                    if part and part not in ["services", "service", "modules", "module", "handlers", "controllers", "apis", "endpoints"]:
                        return part
        
        # Check for known service names in path
        for service_name in self.SERVICE_NAMES.keys():
            if service_name in path_lower:
                return service_name
        
        return None
    
    def _identify_service_from_text(self, text: str) -> str | None:
        """Identify service from text."""
        text_lower = text.lower()
        
        # Check for known service names
        for service_name in self.SERVICE_NAMES.keys():
            if service_name in text_lower:
                return service_name
        
        # Check for service class patterns
        for service_name, patterns in self.SERVICE_NAMES.items():
            for pattern in patterns:
                if pattern.lower() in text_lower:
                    return service_name
        
        return None
    
    def _detect_service_dependencies(self, func_text: str, current_service: str) -> list[str]:
        """Detect service dependencies from function text."""
        dependencies = []
        text_lower = func_text.lower() if func_text else ""
        
        # Look for imports/usage of other services
        for service_name in self.SERVICE_NAMES.keys():
            if service_name != current_service and service_name in text_lower:
                dependencies.append(service_name)
        
        return dependencies
    
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