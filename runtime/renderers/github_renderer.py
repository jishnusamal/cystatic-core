"""GitHub renderer for EngineeringDiscoveryArtifact.

Produces Markdown comments for GitHub pull requests using Jinja2 templates.
This is a dumb presentation layer - all computation is done in the model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, Template

from operational.model import OperationalChangeModel, EngineeringDiscoveryArtifact
from runtime.errors import RendererFailed

class GitHubRenderer:
    """
    Renders OperationalChangeModel to GitHub Markdown comments.
    
    Uses Jinja2 templates to produce formatted Markdown suitable for
    GitHub pull request comments.
    """
    
    def __init__(self, template_dir: str | Path = "templates") -> None:
        """
        Initialize the renderer with template directory.
        
        Args:
            template_dir: Directory containing Jinja2 templates
        """
        self.template_dir = Path(template_dir)
        self._env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._template = self._env.get_template("github_comment.md.j2")
    
    def render(self, ocm: OperationalChangeModel, context: dict[str, Any]) -> str:
        """
        Render an OperationalChangeModel to GitHub Markdown.
        
        Args:
            ocm: OperationalChangeModel to render
            context: Additional context for rendering (repo, pr_number, etc.)
            
        Returns:
            Markdown string suitable for GitHub comment
            
        Raises:
            RendererFailed: If rendering fails
        """
        try:
            # Convert OCM to dictionary
            rendered_data = self._prepare_render_data(ocm)
            
            # Merge with context
            template_context = {**rendered_data, **context}
            
            # Render template
            return self._template.render(**template_context)
        except Exception as exc:
            raise RendererFailed(
                f"Failed to render GitHub comment: {exc}",
                details={"error": str(exc)},
            ) from exc
    
    def _prepare_render_data(self, ocm: OperationalChangeModel) -> dict[str, Any]:
        """
        Prepare OperationalChangeModel data for template rendering.
        
        Args:
            ocm: OperationalChangeModel to prepare
            
        Returns:
            Dictionary with rendered data for template
        """
        data: dict[str, Any] = {}
        
        # Repository info
        data["repository"] = ocm.repository.metadata.get("root_path", "")
        data["language"] = ocm.repository.metadata.get("language", "unknown")
        
        # Change data
        data["change"] = {
            "added_symbols_count": len(ocm.change.added_symbols),
            "removed_symbols_count": len(ocm.change.removed_symbols),
            "modified_symbols_count": len(ocm.change.modified_symbols),
            "changed_imports_count": len(ocm.change.changed_imports),
            "changed_endpoints_count": len(ocm.change.changed_endpoints),
            "files_changed": getattr(ocm.change, 'files_changed', 0),
            "added_symbols": [self._render_symbol(s) for s in ocm.change.added_symbols],
            "removed_symbols": [self._render_symbol(s) for s in ocm.change.removed_symbols],
            "modified_symbols": [
                {
                    "symbol": self._render_symbol(m.symbol),
                    "changes": [self._render_change_type(c) for c in m.changes],
                }
                for m in ocm.change.modified_symbols
            ],
            "changed_imports": [
                {
                    "file": imp.file,
                    "change_type": imp.change_type,
                    "old_import": imp.old_import,
                    "new_import": imp.new_import,
                }
                for imp in ocm.change.changed_imports
            ],
            "changed_endpoints": [
                {
                    "symbol_id": ep.symbol_id,
                    "change_type": ep.change_type,
                    "old_method": ep.old_method,
                    "new_method": ep.new_method,
                    "old_endpoint": ep.old_endpoint,
                    "new_endpoint": ep.new_endpoint,
                }
                for ep in ocm.change.changed_endpoints
            ],
        }
        
        # Behavior data
        data["behavior"] = {
            "behaviors_count": len(ocm.behavior.behaviors),
            "execution_graphs_count": len(ocm.behavior.execution_graphs),
            "behaviors": [self._render_behavior(b) for b in ocm.behavior.behaviors],
            "execution_graphs": [self._render_execution_graph(g) for g in ocm.behavior.execution_graphs],
        }
        
        # Optional models - just mark as present/defined
        if ocm.has_dependency_model():
            data["dependency"] = True
        
        if ocm.has_data_model():
            data["data"] = True
        
        if ocm.has_event_model():
            data["event"] = True
        
        if ocm.has_api_model():
            data["api"] = True
        
        if ocm.has_validation_model():
            data["validation"] = True
        
        if ocm.has_metrics_model():
            data["metrics"] = True
        
        return data
    
    def _render_symbol(self, symbol: Any) -> dict[str, Any]:
        """Render a symbol for template."""
        return {
            "id": symbol.id,
            "name": symbol.name,
            "type": symbol.kind.value if hasattr(symbol.kind, 'value') else str(symbol.kind),
            "file_path": symbol.file,
            "line_number": symbol.start_line,
        }
    
    def _render_change_type(self, change: Any) -> dict[str, Any]:
        """Render a change type for template."""
        return {
            "type": change.change_type if hasattr(change, 'change_type') else type(change).__name__,
        }
    
    def _render_behavior(self, behavior: Any) -> dict[str, Any]:
        """Render a behavior for template."""
        return {
            "id": behavior.id,
            "name": behavior.name,
            "type": behavior.kind.value if hasattr(behavior.kind, 'value') else str(behavior.kind),
            "entry_point": behavior.entry_point,
            "root_symbol_id": behavior.root_symbol_id,
            "changed_symbols_count": len(behavior.changed_symbol_ids),
        }
    
    def _render_execution_graph(self, graph: Any) -> dict[str, Any]:
        """Render an execution graph for template."""
        return {
            "behavior_id": graph.behavior_id,
            "nodes_count": len(graph.nodes) if hasattr(graph, 'nodes') else 0,
            "edges_count": len(graph.edges) if hasattr(graph, 'edges') else 0,
        }
    
    def render_artifact(self, artifact: EngineeringDiscoveryArtifact, context: dict[str, Any]) -> str:
        """
        Render an EngineeringDiscoveryArtifact to GitHub Markdown.
        
        This is the main render method for the execution-oriented architecture.
        
        Args:
            artifact: EngineeringDiscoveryArtifact to render
            context: Additional context for rendering (repo, pr_number, etc.)
            
        Returns:
            Markdown string suitable for GitHub comment
            
        Raises:
            RendererFailed: If rendering fails
        """
        try:
            # Convert artifact to dictionary
            rendered_data = self._prepare_artifact_data(artifact)
            
            # Merge with context
            template_context = {**rendered_data, **context}
            
            # Render template
            return self._template.render(**template_context)
        except Exception as exc:
            raise RendererFailed(
                f"Failed to render GitHub comment: {exc}",
                details={"error": str(exc)},
            ) from exc
    
    def _prepare_artifact_data(self, artifact: EngineeringDiscoveryArtifact) -> dict[str, Any]:
        """
        Prepare EngineeringDiscoveryArtifact data for template rendering.
        
        This is a dumb presentation layer - all computation is done in the model.
        
        Args:
            artifact: EngineeringDiscoveryArtifact to prepare
            
        Returns:
            Dictionary with rendered data for template
        """
        data: dict[str, Any] = {}
        
        # Repository info
        data["repository"] = artifact.repository.metadata.get("root_path", "")
        data["language"] = artifact.repository.metadata.get("language", "unknown")
        
        # Change data
        data["change"] = {
            "added_symbols_count": len(artifact.change.added_symbols),
            "removed_symbols_count": len(artifact.change.removed_symbols),
            "modified_symbols_count": len(artifact.change.modified_symbols),
            "changed_imports_count": len(artifact.change.changed_imports),
            "changed_endpoints_count": len(artifact.change.changed_endpoints),
            "added_symbols": [self._render_symbol(s) for s in artifact.change.added_symbols],
            "removed_symbols": [self._render_symbol(s) for s in artifact.change.removed_symbols],
            "modified_symbols": [
                {
                    "symbol": self._render_symbol(m.symbol),
                    "changes": [self._render_change_type(c) for c in m.changes],
                }
                for m in artifact.change.modified_symbols
            ],
        }
        
        # Execution-oriented abstractions
        data["execution"] = {
            "execution_units_count": len(artifact.execution_units),
            "execution_chains_count": len(artifact.execution_chains),
            "entry_points_count": len(artifact.entry_points),
            "terminal_points_count": len(artifact.terminal_points),
            "shared_executions_count": len(artifact.shared_executions),
            "reachable_units_count": len(artifact.reachable_units),
            "execution_depth": artifact.execution_depth,
            "behaviors": [self._render_behavior(b) for b in artifact.get_behaviors()],
            "entry_points": [self._render_entry_point(ep) for ep in artifact.entry_points],
            "terminal_points": [self._render_terminal_point(tp) for tp in artifact.terminal_points],
            "shared_executions": [self._render_shared_execution(se) for se in artifact.shared_executions],
        }
        
        # Optional models - just mark as present/defined
        if artifact.has_dependency_model():
            data["dependency"] = True
        
        if artifact.has_data_model():
            data["data"] = True
        
        if artifact.has_event_model():
            data["event"] = True
        
        if artifact.has_api_model():
            data["api"] = True
        
        if artifact.has_validation_model():
            data["validation"] = True
        
        if artifact.has_metrics_model():
            data["metrics"] = True
        
        return data
    
    def _render_entry_point(self, ep: Any) -> dict[str, Any]:
        """Render an entry point for template."""
        return {
            "id": ep.id,
            "behavior_id": ep.behavior_id,
            "symbol_id": ep.symbol_id,
            "kind": ep.kind,
            "route": ep.route,
        }
    
    def _render_terminal_point(self, tp: Any) -> dict[str, Any]:
        """Render a terminal point for template."""
        return {
            "id": tp.id,
            "behavior_id": tp.behavior_id,
            "symbol_id": tp.symbol_id,
            "kind": tp.kind,
        }
    
    def _render_shared_execution(self, se: Any) -> dict[str, Any]:
        """Render a shared execution for template."""
        return {
            "id": se.id,
            "symbol_id": se.symbol_id,
            "used_by_count": len(se.used_by),
            "used_by": list(se.used_by),
        }
    
    def render_simple(self, ocm: OperationalChangeModel) -> str:
        """
        Render a simple summary without full template.
        
        Useful for quick summaries or when template is not available.
        
        Args:
            ocm: OperationalChangeModel to render
            
        Returns:
            Simple Markdown summary
        """
        lines = [
            "# Cystatic Analysis",
            "",
            "## Summary",
            f"- **Language:** {ocm.repository.metadata.get('language', 'unknown')}",
            f"- **Files:** {len(ocm.repository.metadata.get('files', {}))}",
            f"- **Symbols:** {len(ocm.repository.symbols)}",
            "",
            "## Changes",
            f"- **Added:** {len(ocm.change.added_symbols)} symbols",
            f"- **Removed:** {len(ocm.change.removed_symbols)} symbols",
            f"- **Modified:** {len(ocm.change.modified_symbols)} symbols",
            f"- **Imports changed:** {len(ocm.change.changed_imports)}",
            f"- **Endpoints changed:** {len(ocm.change.changed_endpoints)}",
            "",
            "## Behavior",
            f"- **Behaviors:** {len(ocm.behavior.behaviors)}",
            f"- **Execution graphs:** {len(ocm.behavior.execution_graphs)}",
        ]
        
        if ocm.has_dependency_model():
            lines.extend(["", "## Dependency Surface", "Dependency changes detected."])
        
        if ocm.has_data_model():
            lines.extend(["", "## Data Surface", "Data model changes detected."])
        
        if ocm.has_event_model():
            lines.extend(["", "## Events", "Event changes detected."])
        
        if ocm.has_api_model():
            lines.extend(["", "## APIs", "API changes detected."])
        
        return "\n".join(lines)