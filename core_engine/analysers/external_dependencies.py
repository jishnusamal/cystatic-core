"""
External Dependency Analyzer

Identifies external system integrations and provider dependencies.
This identifies integrations and provider-specific risk.

Produces evidence types:
- calls_external_system
- depends_on_provider
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext
from core_engine.models.enums import EvidenceType


class ExternalDependencyAnalyzer(EvidenceAnalyzer):
    """Identify external system integrations and provider dependencies.
    
    This analyzer:
    - Detects external API calls and integrations
    - Identifies third-party service dependencies
    - Maps provider-specific risk areas
    - Never predicts failures
    - Only extracts deterministic external dependency facts
    """
    
    # External system patterns
    EXTERNAL_SYSTEMS = {
        # Payment providers
        "stripe": {
            "patterns": ["stripe", "Stripe", "stripe.api", "stripe.checkout", "stripe.payment"],
            "type": "payment_provider",
            "risk_level": "high",
        },
        "paypal": {
            "patterns": ["paypal", "PayPal", "paypal.rest"],
            "type": "payment_provider",
            "risk_level": "high",
        },
        "braintree": {
            "patterns": ["braintree", "Braintree"],
            "type": "payment_provider",
            "risk_level": "high",
        },
        # Cloud providers
        "aws": {
            "patterns": ["aws", "AWS", "boto3", "s3", "ec2", "lambda", "dynamodb"],
            "type": "cloud_provider",
            "risk_level": "medium",
        },
        "gcp": {
            "patterns": ["gcp", "GCP", "google.cloud", "google.storage"],
            "type": "cloud_provider",
            "risk_level": "medium",
        },
        "azure": {
            "patterns": ["azure", "Azure", "azure.storage"],
            "type": "cloud_provider",
            "risk_level": "medium",
        },
        # Communication services
        "slack": {
            "patterns": ["slack", "Slack", "slack_sdk", "slack.web"],
            "type": "communication",
            "risk_level": "low",
        },
        "twilio": {
            "patterns": ["twilio", "Twilio"],
            "type": "communication",
            "risk_level": "medium",
        },
        "sendgrid": {
            "patterns": ["sendgrid", "SendGrid"],
            "type": "communication",
            "risk_level": "low",
        },
        # Version control
        "github": {
            "patterns": ["github", "GitHub", "PyGithub", "github3.py"],
            "type": "version_control",
            "risk_level": "low",
        },
        # Message queues
        "kafka": {
            "patterns": ["kafka", "Kafka", "kafka-python", "confluent_kafka"],
            "type": "message_queue",
            "risk_level": "medium",
        },
        "rabbitmq": {
            "patterns": ["rabbitmq", "RabbitMQ", "pika"],
            "type": "message_queue",
            "risk_level": "medium",
        },
        # Email services
        "smtp": {
            "patterns": ["smtp", "SMTP", "email.mime", "send_mail"],
            "type": "email",
            "risk_level": "low",
        },
        # Authentication providers
        "oauth": {
            "patterns": ["oauth", "OAuth", "oauth2", "authlib"],
            "type": "authentication",
            "risk_level": "high",
        },
        "jwt": {
            "patterns": ["jwt", "JWT", "pyjwt", "jose"],
            "type": "authentication",
            "risk_level": "high",
        },
    }
    
    # API call patterns
    API_CALL_PATTERNS = [
        "requests.get(",
        "requests.post(",
        "requests.put(",
        "requests.delete(",
        "requests.patch(",
        "httpx.get(",
        "httpx.post(",
        "aiohttp.ClientSession",
        "urllib.request",
        "http.client",
    ]
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract external dependencies from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files and changed functions.
            
        Returns:
            AnalyzerOutput with external dependency evidence.
        """
        output = AnalyzerOutput()
        
        # Track external systems used
        external_systems_used: dict[str, list[str]] = {}  # system_name -> list of symbols
        
        # Extract from enriched files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            changed_functions = file_data.get("changed_functions", [])
            keyword_signals = file_data.get("keyword_signals", [])
            
            # Check changed functions for external dependencies
            for func in changed_functions:
                func_name = self._get_func_name(func)
                if not func_name:
                    continue
                
                func_text = self._get_func_text(func)
                
                # Detect external systems
                systems = self._detect_external_systems(func_text, keyword_signals)
                
                for system_name, system_info in systems.items():
                    if system_name not in external_systems_used:
                        external_systems_used[system_name] = []
                    if func_name not in external_systems_used[system_name]:
                        external_systems_used[system_name].append(func_name)
                    
                    output.impact_evidence.append({
                        "source_symbol": func_name,
                        "target_symbol": system_name,
                        "evidence_type": "calls_external_system",
                        "confidence": 0.85,
                        "explanation": f"Function {func_name} calls {system_name} ({system_info['type']})",
                        "metadata": {
                            "file_path": file_path,
                            "system_name": system_name,
                            "system_type": system_info["type"],
                            "risk_level": system_info["risk_level"],
                        },
                    })
            
            # Check keyword signals for external system hints
            for signal in keyword_signals:
                signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
                systems = self._detect_external_systems(signal_text, [])
                
                for system_name, system_info in systems.items():
                    if system_name not in external_systems_used:
                        external_systems_used[system_name] = []
                    if file_path not in external_systems_used[system_name]:
                        external_systems_used[system_name].append(file_path)
                    
                    output.impact_evidence.append({
                        "source_symbol": file_path,
                        "target_symbol": system_name,
                        "evidence_type": "depends_on_provider",
                        "confidence": 0.6,
                        "explanation": f"Keyword signal suggests dependency on {system_name}",
                        "metadata": {
                            "keyword": signal_text,
                            "system_name": system_name,
                            "system_type": system_info["type"],
                        },
                    })
        
        # Generate shared external system evidence
        # If multiple functions use the same external system, they're connected
        for system_name, symbols in external_systems_used.items():
            if len(symbols) > 1:
                for i, sym1 in enumerate(symbols):
                    for sym2 in symbols[i+1:]:
                        output.impact_evidence.append({
                            "source_symbol": sym1,
                            "target_symbol": sym2,
                            "evidence_type": "shared_external_system",
                            "confidence": 0.7,
                            "explanation": f"Both depend on {system_name}",
                            "metadata": {
                                "system_name": system_name,
                            },
                        })
        
        return output
    
    def _detect_external_systems(self, text: str, keyword_signals: list) -> dict[str, dict[str, str]]:
        """Detect external systems in text.
        
        Args:
            text: Text to analyze
            keyword_signals: List of keyword signals from analysis
            
        Returns:
            Dictionary mapping system names to system info
        """
        systems = {}
        text_lower = text.lower() if text else ""
        
        # Check for external system patterns
        for system_name, system_info in self.EXTERNAL_SYSTEMS.items():
            for pattern in system_info["patterns"]:
                if pattern.lower() in text_lower:
                    systems[system_name] = system_info
                    break
        
        # Check for API call patterns
        has_api_call = any(pattern.lower() in text_lower for pattern in self.API_CALL_PATTERNS)
        if has_api_call:
            # If we have API calls but no specific system identified, mark as generic external
            if "generic_http" not in systems:
                systems["generic_http"] = {
                    "type": "http_api",
                    "risk_level": "medium",
                }
        
        # Check keyword signals
        for signal in keyword_signals:
            signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
            signal_lower = signal_text.lower()
            
            for system_name, system_info in self.EXTERNAL_SYSTEMS.items():
                for pattern in system_info["patterns"]:
                    if pattern.lower() in signal_lower:
                        systems[system_name] = system_info
                        break
        
        return systems
    
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