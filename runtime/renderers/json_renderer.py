"""JSON renderer for OperationalChangeModel and EngineeringDiscoveryModel.

Produces a pure machine-readable dictionary representation.
No formatting, no markdown - just serialization.
"""

from __future__ import annotations

from typing import Any

from operational.model import OperationalChangeModel, EngineeringDiscoveryModel
from runtime.errors import JSONSerializationFailed, RendererFailed


class JSONRenderer:
    """
    Renders models to a plain dictionary.
    
    This is the simplest renderer - pure serialization with no formatting.
    Used for API responses and programmatic consumption.
    Accepts both OperationalChangeModel and EngineeringDiscoveryModel.
    """
    
    def render(self, model: OperationalChangeModel | EngineeringDiscoveryModel) -> dict[str, Any]:
        """
        Render a model to a dictionary.
        
        Args:
            model: OperationalChangeModel or EngineeringDiscoveryModel to render
            
        Returns:
            Dictionary representation of the model
            
        Raises:
            RendererFailed: If rendering fails
        """
        try:
            if isinstance(model, EngineeringDiscoveryModel):
                return self._render_discovery_model(model)
            return self._render_operational_model(model)
        except Exception as exc:
            raise RendererFailed(
                f"Failed to render model: {exc}",
                details={"error": str(exc)},
            ) from exc
    
    def _render_operational_model(self, ocm: OperationalChangeModel) -> dict[str, Any]:
        """
        Recursively render the operational model and all its components.
        
        Args:
            ocm: OperationalChangeModel to render
            
        Returns:
            Dictionary representation
        """
        result: dict[str, Any] = {}
        
        # Core models (always present)
        result["repository"] = self._render_repository(ocm.repository)
        result["change"] = self._render_change(ocm.change)
        result["behavior"] = self._render_behavior(ocm.behavior)
        
        # Optional enrichment models
        if ocm.has_dependency_model():
            result["dependency"] = self._render_dependency(ocm.dependency)
        
        if ocm.has_data_model():
            result["data"] = self._render_data(ocm.data)
        
        if ocm.has_event_model():
            result["event"] = self._render_event(ocm.event)
        
        if ocm.has_api_model():
            result["api"] = self._render_api(ocm.api)
        
        if ocm.has_validation_model():
            result["validation"] = self._render_validation(ocm.validation)
        
        if ocm.has_metrics_model():
            result["metrics"] = self._render_metrics(ocm.metrics)
        
        # Metadata
        result["_meta"] = {
            "model_type": "OperationalChangeModel",
            "populated_models": ocm.populated_optional_models,
        }
        
        return result
    
    def _render_discovery_model(self, edm: EngineeringDiscoveryModel) -> dict[str, Any]:
        """
        Recursively render the engineering discovery model and all its components.
        
        Args:
            edm: EngineeringDiscoveryModel to render
            
        Returns:
            Dictionary representation
        """
        result: dict[str, Any] = {}
        
        # Core models (always present)
        result["repository"] = self._render_repository(edm.repository)
        result["change"] = self._render_change(edm.change)
        result["behavior"] = self._render_behavior(edm.behavior)
        
        # Execution-oriented abstractions
        result["execution"] = {
            "execution_units_count": len(edm.execution_units),
            "execution_chains_count": len(edm.execution_chains),
            "entry_points_count": len(edm.entry_points),
            "terminal_points_count": len(edm.terminal_points),
            "shared_executions_count": len(edm.shared_executions),
            "reachable_units_count": len(edm.reachable_units),
            "execution_depth": edm.execution_depth,
        }
        
        # Optional enrichment models
        if edm.has_dependency_model():
            result["dependency"] = self._render_dependency(edm.dependency)
        
        if edm.has_data_model():
            result["data"] = self._render_data(edm.data)
        
        if edm.has_event_model():
            result["event"] = self._render_event(edm.event)
        
        if edm.has_api_model():
            result["api"] = self._render_api(edm.api)
        
        if edm.has_validation_model():
            result["validation"] = self._render_validation(edm.validation)
        
        if edm.has_metrics_model():
            result["metrics"] = self._render_metrics(edm.metrics)
        
        # Metadata
        result["_meta"] = {
            "model_type": "EngineeringDiscoveryModel",
            "populated_models": edm.populated_optional_models,
        }
        
        return result
    
    def _render_repository(self, repository: Any) -> dict[str, Any]:
        """Render RepositoryModel to dictionary."""
        return {
            "language": repository.metadata.get("language", "unknown"),
            "root_path": repository.metadata.get("root_path", ""),
            "files_count": len(repository.metadata.get("files", {})),
            "symbols_count": len(repository.symbols),
            "imports_count": len(repository.metadata.get("imports", [])),
        }
    
    def _render_change(self, change: Any) -> dict[str, Any]:
        """Render ChangeModel to dictionary."""
        return {
            "added_symbols_count": len(change.added_symbols),
            "removed_symbols_count": len(change.removed_symbols),
            "modified_symbols_count": len(change.modified_symbols),
            "changed_imports_count": len(change.changed_imports),
            "changed_endpoints_count": len(change.changed_endpoints),
            "files_changed": getattr(change, 'files_changed', 0),
            "added_symbols": [self._render_symbol_summary(s) for s in change.added_symbols],
            "removed_symbols": [self._render_symbol_summary(s) for s in change.removed_symbols],
            "modified_symbols": [
                {
                    "symbol": self._render_symbol_summary(m.symbol),
                    "changes": [self._render_change_type(c) for c in m.changes],
                }
                for m in change.modified_symbols
            ],
            "changed_imports": [
                {
                    "file": imp.file,
                    "old_import": imp.old_import,
                    "new_import": imp.new_import,
                    "change_type": imp.change_type,
                }
                for imp in change.changed_imports
            ],
            "changed_endpoints": [
                {
                    "symbol_id": ep.symbol_id,
                    "old_endpoint": ep.old_endpoint,
                    "new_endpoint": ep.new_endpoint,
                    "old_method": ep.old_method,
                    "new_method": ep.new_method,
                    "change_type": ep.change_type,
                }
                for ep in change.changed_endpoints
            ],
        }
    
    def _render_behavior(self, behavior: Any) -> dict[str, Any]:
        """Render BehaviorModel to dictionary."""
        return {
            "behaviors_count": len(behavior.behaviors),
            "execution_graphs_count": len(behavior.execution_graphs),
            "behaviors": [self._render_behavior_summary(b) for b in behavior.behaviors],
            "execution_graphs": [self._render_execution_graph(g) for g in behavior.execution_graphs],
        }
    
    def _render_dependency(self, dependency: Any) -> dict[str, Any]:
        """Render DependencyModel to dictionary."""
        try:
            from dataclasses import asdict
            return asdict(dependency)
        except Exception:
            return {"type": type(dependency).__name__}
    
    def _render_data(self, data: Any) -> dict[str, Any]:
        """Render DataModel to dictionary."""
        try:
            from dataclasses import asdict
            return asdict(data)
        except Exception:
            return {"type": type(data).__name__}
    
    def _render_event(self, event: Any) -> dict[str, Any]:
        """Render EventModel to dictionary."""
        try:
            from dataclasses import asdict
            return asdict(event)
        except Exception:
            return {"type": type(event).__name__}
    
    def _render_api(self, api: Any) -> dict[str, Any]:
        """Render APIModel to dictionary."""
        try:
            from dataclasses import asdict
            return asdict(api)
        except Exception:
            return {"type": type(api).__name__}
    
    def _render_validation(self, validation: Any) -> dict[str, Any]:
        """Render ValidationModel to dictionary."""
        try:
            from dataclasses import asdict
            return asdict(validation)
        except Exception:
            return {"type": type(validation).__name__}
    
    def _render_metrics(self, metrics: Any) -> dict[str, Any]:
        """Render metrics to dictionary."""
        try:
            from dataclasses import asdict
            return asdict(metrics)
        except Exception:
            return {"type": type(metrics).__name__}
    
    def _render_symbol_summary(self, symbol: Any) -> dict[str, Any]:
        """Render a symbol to a summary dictionary."""
        return {
            "id": symbol.id,
            "name": symbol.name,
            "type": symbol.kind.value if hasattr(symbol.kind, 'value') else str(symbol.kind),
            "file_path": symbol.file,
            "line_number": symbol.start_line,
        }
    
    def _render_change_type(self, change: Any) -> dict[str, Any]:
        """Render a change type to dictionary."""
        try:
            from dataclasses import asdict
            return asdict(change)
        except Exception:
            return {"type": type(change).__name__}
    
    def _render_behavior_summary(self, behavior: Any) -> dict[str, Any]:
        """Render a behavior to a summary dictionary."""
        return {
            "id": behavior.id,
            "name": behavior.name,
            "kind": behavior.kind.value if hasattr(behavior.kind, 'value') else str(behavior.kind),
            "entry_point": behavior.entry_point,
            "root_symbol_id": behavior.root_symbol_id,
            "changed_symbol_ids": list(behavior.changed_symbol_ids),
        }
    
    def _render_execution_graph(self, graph: Any) -> dict[str, Any]:
        """Render an execution graph to dictionary."""
        return {
            "behavior_id": graph.behavior_id,
            "nodes_count": len(graph.nodes) if hasattr(graph, 'nodes') else 0,
            "edges_count": len(graph.edges) if hasattr(graph, 'edges') else 0,
            "node_ids": [n.symbol_id for n in graph.nodes] if hasattr(graph, 'nodes') else [],
            "edges": [
                {"caller_id": e.caller_id, "callee_id": e.callee_id, "call_type": e.call_type}
                for e in graph.edges
            ] if hasattr(graph, 'edges') else [],
        }